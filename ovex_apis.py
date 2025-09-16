

from datetime import time
import hashlib
import hmac
import os
from dotenv import load_dotenv
import requests
from variables import OVEX_BASE_URL

load_dotenv() 

OVEX_API_KEY = os.getenv('OVEX_API_KEY')
OVEX_SECRET = os.getenv('OVEX_SECRET')

def auth_headers(method: str, path: str, body: str = ""):
    """Build headers for OVEX. Adapt this to the spec (may be simple Bearer or HMAC)."""
    ts = str(int(time.time()))
    message = ts + method.upper() + path + body
    signature = hmac.new(OVEX_API_KEY.encode(), message.encode(), hashlib.sha256).hexdigest() if OVEX_SECRET else None
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": OVEX_API_KEY or "",
        "X-TS": ts,
    }
    if signature:
        headers["X-SIGNATURE"] = signature
    return headers

def place_order(data):
    # data = request.get_json(force=True)
    quote_id = data.get('quote_id')
    if not quote_id:
        return ("Missing quote_id", 400)

    path = f"/orders"
    url = OVEX_BASE_URL + path
    payload = {"quote_id": quote_id}
    res = requests.post(url, json=payload, headers=auth_headers("POST", path, body=requests.utils.json.dumps(payload)))

    if res.status_code >= 300:
        return (res.text, res.status_code)

    r = res.json()
    return {
        "order_id": r.get("id") or r.get("order_id"),
        "status": r.get("status"),
    }
    
def create_quote(data):
    # data = request.get_json(force=True)
    pair = data.get('pair')           # e.g. "BTC-GHS"
    side = data.get('side')           # "buy" | "sell"
    amount_crypto = data.get('amount_crypto')
    amount_fiat   = data.get('amount_fiat')

    if not pair or side not in ("buy","sell"):
        return ("Invalid pair/side", 400)

    payload = {
        "pair": pair,
        "side": side,
        # Many quote APIs accept exactly one of these. Send whichever the user filled.
        **({"amount_crypto": str(amount_crypto)} if amount_crypto else {}),
        **({"amount_fiat": str(amount_fiat)} if amount_fiat else {}),
    }

    path = "/quotes"
    url = OVEX_BASE_URL + path
    res = requests.post(url, json=payload, headers=auth_headers("POST", path, body=requests.utils.json.dumps(payload)))

    if res.status_code >= 300:
        return (res.text, res.status_code)

    # Normalize response to the front‑end shape
    r = res.json()
    return {
        "quote_id": r.get("id") or r.get("quote_id"),
        "price": r.get("price") or r.get("rate"),
        "fee": r.get("fee", 0),
        "total": r.get("total") or r.get("amount_total") or r.get("amount_fiat"),
        "amount_crypto": r.get("amount_crypto") or r.get("amount_base"),
        "amount_fiat": r.get("amount_fiat") or r.get("amount_quote"),
        "expires_at": r.get("expires_at") or r.get("expiry")
    }