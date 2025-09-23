# idempotency.py
import json
import hashlib
import base64
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message
from redis.asyncio import Redis

SAFE_HEADER_WHITELIST = {
    "content-type",
    "cache-control",
    "content-disposition",
    "content-language",
    "etag",
    "expires",
    "last-modified",
    "location",
    "retry-after",
}

def normalize_json_body(raw: bytes) -> bytes:
    """Ensure consistent hashing for semantically equal JSON bodies."""
    if not raw:
        return b""
    try:
        parsed = json.loads(raw)
        return json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode("utf-8")
    except Exception:
        # Non-JSON payloads are hashed as-is
        return raw

def body_hash(method: str, path: str, body: bytes) -> str:
    h = hashlib.sha256()
    h.update(method.upper().encode())
    h.update(b"|")
    h.update(path.encode())
    h.update(b"|")
    h.update(body)
    return h.hexdigest()

def build_key(
    api_key: str, method: str, path: str, idem_key: str
) -> str:
    # Scope by api key, method, and normalized path
    return f"idem:{api_key}:{method.upper()}:{path}:{idem_key}"

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware that enforces idempotency with Redis.

    Requirements:
      - Client must send `Idempotency-Key` header (UUID or opaque).
      - Optional: client sends `x-api-key` (you already use this in Vaulta).
    """

    def __init__(
        self,
        app,
        redis: Redis,
        ttl_seconds: int = 60 * 60 * 24,  # 24h
        require_header: bool = True,
    ):
        super().__init__(app)
        self.redis = redis
        self.ttl = ttl_seconds
        self.require_header = require_header

    async def dispatch(self, request: Request, call_next):
        # Only protect write operations
        if request.method.upper() not in {"POST", "PUT", "PATCH", "DELETE"}:
            return await call_next(request)

        idem_key = request.headers.get("Idempotency-Key")
        if self.require_header and not idem_key:
            return Response(
                content=json.dumps({"error": "Missing Idempotency-Key header"}),
                status_code=400,
                media_type="application/json",
            )

        # Read and buffer the request body so we can hash it and re-inject it
        raw_body = await request.body()
        normalized_body = normalize_json_body(raw_body)
        req_hash = body_hash(request.method, request.url.path, normalized_body)

        # Re-inject body for downstream (since we consumed it)
        async def receive() -> Message:
            return {"type": "http.request", "body": raw_body, "more_body": False}
        request._receive = receive  # type: ignore

        api_key = request.headers.get("x-api-key", "anon")
        redis_key = build_key(api_key, request.method, request.url.path, idem_key or "auto")

        # Reserve or check existing
        existing_raw = self.redis.get(redis_key)
        if existing_raw:
            try:
                existing = json.loads(existing_raw)
            except Exception:
                existing = {}

            status = existing.get("status")
            stored_hash = existing.get("req_hash")

            if status == "completed":
                if stored_hash != req_hash:
                    return Response(
                        content=json.dumps({
                            "error": "Idempotency-Key reuse with different request body",
                            "hint": "Generate a fresh Idempotency-Key for changed payloads."
                        }),
                        status_code=409,
                        media_type="application/json",
                    )
                # Replay stored response
                resp_data = existing.get("response", {})
                status_code = int(resp_data.get("status_code", 200))
                body_b64 = resp_data.get("body_b64", "")
                headers = resp_data.get("headers", {})

                body_bytes = base64.b64decode(body_b64) if body_b64 else b""
                response = Response(content=body_bytes, status_code=status_code)
                for k, v in headers.items():
                    response.headers[k] = v
                response.headers["X-Idempotent-Replay"] = "true"
                return response

            if status == "processing":
                # Another request with same key is in-flight
                response = Response(
                    content=json.dumps({
                        "error": "Request with this Idempotency-Key is still processing. Try again.",
                    }),
                    status_code=409,
                    media_type="application/json",
                )
                response.headers["Retry-After"] = "5"
                return response

            # Fallthrough: malformed/unknown → try to overwrite safely
            # (very rare; treat like new)
        
        # Attempt to reserve key (atomic)
        reservation = {
            "status": "processing",
            "req_hash": req_hash,
            "created_at": now_iso(),
        }
        ok = self.redis.set(redis_key, json.dumps(reservation), ex=self.ttl, nx=True)
        if not ok:
            # Race: someone else reserved between GET and SETNX
            return Response(
                content=json.dumps({
                    "error": "Request with this Idempotency-Key is still processing. Try again.",
                }),
                status_code=409,
                media_type="application/json",
            )

        # Call downstream and capture the body for storage
        # We must fully materialize the response body
        downstream_response = await call_next(request)

        # Read/clone body (works for plain & streaming responses)
        body_chunks = []
        async for chunk in downstream_response.body_iterator:
            body_chunks.append(chunk)
        body_bytes = b"".join(body_chunks)

        # Rebuild a fresh Response to return (since we've consumed the iterator)
        out = Response(
            content=body_bytes,
            status_code=downstream_response.status_code,
            media_type=downstream_response.media_type,
        )
        # Copy whitelisted headers
        saved_headers: Dict[str, str] = {}
        for k, v in downstream_response.headers.items():
            lk = k.lower()
            if lk in SAFE_HEADER_WHITELIST:
                out.headers[k] = v
                saved_headers[k] = v

        # Persist final state
        to_store = {
            "status": "completed",
            "req_hash": req_hash,
            "created_at": reservation["created_at"],
            "completed_at": now_iso(),
            "response": {
                "status_code": out.status_code,
                "headers": saved_headers,
                "body_b64": base64.b64encode(body_bytes).decode("ascii"),
            },
        }
        # Use pipeline so we both set value and ensure TTL is present
        with self.redis.pipeline(transaction=True) as pipe:
            pipe.set(redis_key, json.dumps(to_store)).expire(redis_key, self.ttl).execute()

        out.headers["X-Idempotent-Replay"] = "false"
        return out