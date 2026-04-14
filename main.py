import os
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from httpcore import request
from pydantic import BaseModel, EmailStr, Field
from typing import Dict, List, Annotated, Optional
import secrets
import random
import uuid
import json
from datetime import datetime, timedelta

from authstore import save_access_token, save_user_otp

from starlette.requests import Request

import resend
import authstore
from database import engine, SessionLocal
import services
from vaulta_idempotency import IdempotencyMiddleware
import models
from sqlalchemy.orm import Session

from services import get_customer_by_email, issue_jwt_token, send_otp_to_email_for_login
from utils import generate_otp, send_email, send_slack, send_private_slack, send_slack_message, send_slack_file
from fastapi import Body
import hashlib
import jwt
from fastapi.security import OAuth2PasswordBearer

from ovex_apis import create_quote, get_trade_history
from ovex_apis import get_markets
from redis_client import r
from fastapi import Query, File, UploadFile, Form
from fastapi import Request
import inspect
from firebase_storage import upload_documents
import httpx
from core.config import settings

app = FastAPI()

import logging
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s"
)

# Create loggers for different modules
logger_onboarding = logging.getLogger("vaulta.onboarding")
logger_auth = logging.getLogger("vaulta.auth")
logger_payments = logging.getLogger("vaulta.payments")
logger_accounts = logging.getLogger("vaulta.accounts")
logger_transactions = logging.getLogger("vaulta.transactions")
logger_errors = logging.getLogger("vaulta.errors")
logger = logger_onboarding  # Keep for backward compatibility

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())
    error_msg = str(exc)
    tb = traceback.format_exc()
    
    logger_errors.error(f"[{error_id}] {exc.__class__.__name__}: {error_msg}\n{tb}")
    
    # Send to Slack
    try:
        slack_message = f"🚨 *Backend Error* [{error_id}]\nPath: {request.url.path}\nMethod: {request.method}\nError: {error_msg}"
        send_slack_message("rates", slack_message)
    except Exception as slack_err:
        logger_errors.error(f"Failed to send error to Slack: {slack_err}")
    
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error", "error_id": error_id}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger_errors.warning(f"HTTP {exc.status_code}: {exc.detail} at {request.url.path}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# Add the middleware near the top of your stack
# app.add_middleware(
#     IdempotencyMiddleware,
#     redis=r,
#     ttl_seconds=60*60*24,   # 24h retention
#     require_header=True,    # force Idempotency-Key
# )

# def _api_key_is_enabled(key_obj) -> bool:
#     """Return True if the key is enabled, handling either `.active` or `.is_active` fields."""
#     return bool(getattr(key_obj, "active", getattr(key_obj, "is_active", True)))

# UNPROTECTED_PATHS = {
#     "/",                # health/root
#     "/login",
#     "/register",
#     "/verify-otp",
#     "/account",
#     # API key management endpoints should not require an API key themselves
#     "/api/v1/create_api_key",
#     "/api/v1/api_keys",
#     "/api/v1/toggle_api_key",
#     "/api/v1/delete_api_key",  # wildcard path excluded via startswith check below
# }

# @app.middleware("http")
# async def require_x_api_key(request: Request, call_next):
#     path = request.url.path

#     # Enforce API key for all /api/v1/* routes EXCEPT the explicitly unprotected ones.
#     needs_key = path.startswith("/api/v1/") and not any(
#         path == p or path.startswith(p + "/") for p in UNPROTECTED_PATHS
#     )

#     if needs_key:
#         x_api_key = request.headers.get("x-api-key")
#         if not x_api_key:
#             return JSONResponse(status_code=401, content={"detail": "Missing x-api-key header"})

#         db = SessionLocal()
#         try:
#             key_obj = db.query(models.ApiKey).filter(models.ApiKey.key == x_api_key).first()
#             if not key_obj:
#                 return JSONResponse(status_code=403, content={"detail": "Invalid API key"})

#             # Expiry check (if present)
#             # if getattr(key_obj, "expires_at", None) and key_obj.expires_at < datetime.now():
#             #     return JSONResponse(status_code=403, content={"detail": "API key expired"})

#             # Active/enabled check
#             if not _api_key_is_enabled(key_obj):
#                 return JSONResponse(status_code=403, content={"detail": "API key disabled"})

#             # Optionally expose to downstream handlers
#             request.state.api_key = x_api_key
#             request.state.api_user_id = getattr(key_obj, "user_id", None)
#         finally:
#             db.close()

#     return await call_next(request)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

models.Base.metadata.create_all(bind=engine)

# Mock user database - in a real app, use a proper database
users_db = {}

# Store OTPs with expiration time
otp_store = {}

class ChoiceBase(BaseModel):
    choice_text: str
    is_correct: bool

class QuestionBase(BaseModel):
    question_text: str
    choices: List[ChoiceBase]

class UserLogin(BaseModel):
    email: EmailStr
    # password: str

class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    # password: str

class UserResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    dashboard:dict

class QuoteResponse(BaseModel):
    quote_id: str
    pair: str
    side: str
    amount_crypto: Optional[str]
    amount_fiat: Optional[str]
    price: str
    expires_at: datetime

class QuoteRequest(BaseModel):
    pair: str           # e.g. "BTC-GHS"
    side: str           # "buy" | "sell"
    amount_crypto: Optional[float] = None
    amount_fiat: Optional[float] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class ApiResponse(BaseModel):
    message: str
    code: int
    data: dict
    status: str
    
class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    
class OTPResponse(BaseModel):
    otp: str
    expires_in: int  # seconds
    
class ResetPasswordRequest(BaseModel):
    email: EmailStr
    otp: str
    new_password: str


class UboStartRequest(BaseModel):
    reference_id: str
    full_name: str
    email: EmailStr
    phone: str
    ownership_percentage: float = Field(..., gt=0, le=100)


class UboVerifyRequest(BaseModel):
    ubo_reference_id: str
    inquiry_id: str


ALLOWED_PERSONA_STATUSES = {"completed", "approved"}


def _is_user_verified_for_login(user: models.User) -> bool:
    return bool(getattr(user, "verified", False))
    
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def _fetch_persona_inquiry_attributes(inquiry_id: str, context_email: str = "", context_phone: str = "") -> dict:
    logger.info(f"[persona] Verifying inquiry_id={inquiry_id}")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"https://withpersona.com/api/v1/inquiries/{inquiry_id}",
            headers={
                "Authorization": f"Bearer {settings.PERSONA_API_KEY}",
                "Persona-Version": "2023-01-05",
                "Key-Inflection": "camel",
            },
        )

    if resp.status_code != 200:
        logger.error(f"[persona] API error: status={resp.status_code}, body={resp.text}")
        send_slack_message(
            "rates",
            f"Persona API error: {resp.status_code} {resp.text}\\n{context_email}\\n{context_phone}\\n{inquiry_id}",
        )
        raise HTTPException(status_code=502, detail="Failed to verify inquiry with Persona")

    inquiry = resp.json().get("data", {})
    attrs = inquiry.get("attributes", {})
    if not attrs:
        logger.error(f"[persona] Empty attributes for inquiry_id={inquiry_id}")
        raise HTTPException(status_code=400, detail="Invalid Persona inquiry response")
    return attrs

@app.post("/login", response_model=ApiResponse, status_code=status.HTTP_200_OK)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    logger_auth.info(f"[login] Request received for email: {user_data.email}")
    
    email = user_data.email
    user = get_customer_by_email(email, db)
    logger_auth.info(f"[login] User lookup: {'found' if user else 'not found'} for {email}")
    
    if not user:
        logger_auth.warning(f"[login] Failed login attempt - user not found: {email}")
        send_private_slack(f"❌ Login attempt failed - user not found: {email}")
        return JSONResponse(
        status_code=404,
        content={"message": "User was not found"}
    )

    if not _is_user_verified_for_login(user):
        logger_auth.warning(f"[login] Failed login attempt - user not verified: {email}")
        send_private_slack(f"❌ Login blocked - user not verified: {email}")
        raise HTTPException(
            status_code=403,
            detail="User is not verified. Please complete onboarding verification before logging in.",
        )
    
    otp = generate_otp()
    to = [user.email]
    
    user.password = otp
    db.commit()
    db.refresh(user)
    logger_auth.info(f"[login] OTP generated and stored for user: {email}")
    
    try:
        send_email("otp.html", f"OTP - {otp}", to, {"name":user.first_name, "otp":otp})
        logger_auth.info(f"[login] OTP email sent successfully to {email}")
    except Exception as e:
        logger_auth.error(f"[login] Failed to send OTP email to {email}: {e}")
        send_private_slack(f"⚠️ Failed to send OTP email to {email}")
    
    send_private_slack(f"✅ Login OTP generated for: {email}")
    
    token = secrets.token_hex(32)
    save_access_token(token, str(user.id))
    save_user_otp(str(user.id), otp)
    
    logger_auth.info(f"[login] Login successful - token issued for: {email}")
    return JSONResponse(
        status_code=200,
        content={"message": f"OTP has been sent to {user.first_name}","access_token": token, "token_type": "bearer"}
    )
    # return ApiResponse(message = "User was not found", code=404, data={"access_token": token, "token_type": "bearer"}, status="Failed")

#verify the otp
class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str
    access_token: str

def _extract_bearer_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None

class VerifyOtpBody(BaseModel):
    otp: str
    token: str

@app.post("/verify-otp")
async def verify_otp(body: VerifyOtpBody, db: Session = Depends(get_db)):
    logger_auth.info(f"[verify-otp] OTP verification request received")
    
    token = body.token
    if not token:
        logger_auth.warning(f"[verify-otp] Missing access token")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    user_id = authstore.get_user_id_from_token(token)
    logger_auth.info(f"[verify-otp] Token resolved to user: {user_id}")
    
    user = authstore.get_user_by_id(user_id)
    
    if not user_id:
        logger_auth.warning(f"[verify-otp] Invalid or expired token")
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    expected_otp = authstore.get_user_otp(user_id)
    logger_auth.info(f"[verify-otp] OTP lookup for user {user_id}")

    if not expected_otp or body.otp != expected_otp:
        logger_auth.warning(f"[verify-otp] Invalid OTP provided for user {user_id}")
        raise HTTPException(status_code=400, detail="Invalid OTP")

    authstore.clear_user_otp(user_id)
    jwt_response = issue_jwt_token(user_id)
    jwt_response['user'] = user

    logger_auth.info(f"[verify-otp] OTP verified successfully for user {user_id}")
    return jwt_response

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_authenticated_user_id(token: str = Depends(oauth2_scheme)) -> str:
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_id

@app.get("/account", response_model=UserResponse)
async def get_account(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    logger_auth.info("[account] Token decode attempt")
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        logger_auth.info(f"[account] User ID extracted: {user_id}")
        if not user_id:
            logger_auth.warning("[account] Invalid token: no user_id")
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError as e:
        logger_auth.error(f"[account] JWT error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        logger_auth.warning(f"[account] User not found: {user_id}")
        raise HTTPException(status_code=404, detail="User not found")
    logger_auth.info(f"[account] Account retrieved for {user.email}")
    
    return {
        "id": str(user.id),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "role": user.role,
        "phone": user.phone,
        "dashboard":{
            "wallet_balance":"39",
            "currency_pair_1":{
                "label":"USDT",
                "value":"1",
                "subvalue":"1"
            },
            "currency_pair_2":{
                "label":"GHS",
                "value":"1",
                "subvalue":"1"
            },
            "summary":
            [
                {
                "Pending Approval":"1",
                },
                {   
                "Risk Alert":"7",
                },
                {   
                "Flagged Transactions":"1"
                }
            ],
            "recent_transactions":[
                {
                    "name":"Received USDT",
                    "date":"2024-06-01",
                    "amount":"$1000",
                    "status":"Completed"
                },
                {
                    "name":"Sent GHS",
                    "date":"2024-06-02",
                    "amount":"GHS 500",
                    "status":"Pending"
                }
            ]
        }
    }

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    
    logger_auth.info(f"[register] New registration: {user_data.email}")
    
    existing = db.query(models.User).filter(models.User.email == user_data.email).first()
    if existing:
        logger_auth.warning(f"[register] Email already registered: {user_data.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    user_id = secrets.token_hex(8)
    logger_auth.info(f"[register] Generated user ID: {user_id}")
    
    new_customer = models.User(
        id = user_id,
        first_name = user_data.first_name,
        last_name = user_data.last_name,
        email = user_data.email,
        phone = user_data.phone,
        verified=False,
        # password = user_data.password  #TODO: In production, hash the password
    )
    
    db.add(new_customer)
    db.commit()
    db.refresh(new_customer)
    print("New customer created with ID:", new_customer.id)
    
    try:
        # send welcome email
        print("Sending welcome email to:", user_data.email)
        send_email("welcome.html","Welcome To Vaulta", to=[new_customer.email],context={"name":new_customer.first_name, "to":[new_customer.email], "subject":f"OTP - {"otp"}"})
    
    except Exception as e:
        print("Error sending welcome email:", str(e))
        
    # Return user data without password
    print("Returning user data")
    return {
        "id": str(new_customer.id),
        "first_name": new_customer.first_name,
        "last_name": new_customer.last_name,
        "email": new_customer.email,
        "phone": new_customer.phone,
        "dashboard":{}
    }

# ── Onboarding (no auth — users don't have accounts yet) ─────

@app.get("/onboarding", include_in_schema=False)
async def onboarding_page():
    return FileResponse("templates/onboarding.html", media_type="text/html")
@app.get("/api/v1/onboarding/start")
async def start_onboarding(db: Session = Depends(get_db)):
    """Generate a reference_id for a new Persona inquiry. No auth required."""
    logger.info("[onboarding/start] Request received")
    try:
        reference_id = f"kyc_{uuid.uuid4().hex[:12]}"
        logger.info(f"[onboarding/start] Generated reference_id={reference_id}")

        kyc = models.UserKyc(reference_id=reference_id, persona_status="pending")
        db.add(kyc)
        db.commit()
        db.refresh(kyc)
        logger.info(f"[onboarding/start] KYC record created, id={kyc.id}")

        response = {
            "reference_id": reference_id,
            "persona_template_id": settings.PERSONA_TEMPLATE_ID,
            "persona_environment": settings.PERSONA_ENVIRONMENT,
        }
        logger.info(f"[onboarding/start] Returning: {response}")
        return response
    except Exception as e:
        logger.exception(f"[onboarding/start] Error: {e}")
        raise


@app.post("/api/v1/onboarding/ubo/start")
async def start_ubo_onboarding(payload: UboStartRequest, db: Session = Depends(get_db)):
    """Create or update a UBO onboarding record and return Persona config."""
    logger.info(
        f"[onboarding/ubo/start] reference_id={payload.reference_id}, email={payload.email}, full_name={payload.full_name}, ownership_percentage={payload.ownership_percentage}"
    )

    kyc = db.query(models.UserKyc).filter(models.UserKyc.reference_id == payload.reference_id).first()
    if not kyc:
        logger.warning(f"[onboarding/ubo/start] KYC not found for reference_id={payload.reference_id}")
        raise HTTPException(status_code=404, detail="Onboarding session not found")

    existing = (
        db.query(models.UserKycUbo)
        .filter(models.UserKycUbo.kyc_id == kyc.id, models.UserKycUbo.email == payload.email)
        .first()
    )

    if existing:
        existing.full_name = payload.full_name
        existing.phone = payload.phone
        existing.ownership_percentage = payload.ownership_percentage
        if existing.persona_status not in ALLOWED_PERSONA_STATUSES:
            existing.persona_status = "pending"
            existing.persona_inquiry_id = None
            existing.verified_at = None
        db.commit()
        db.refresh(existing)
        ubo = existing
        logger.info(f"[onboarding/ubo/start] Reusing existing UBO reference={ubo.ubo_reference_id}")
    else:
        ubo = models.UserKycUbo(
            kyc_id=kyc.id,
            ubo_reference_id=f"ubo_{uuid.uuid4().hex[:12]}",
            full_name=payload.full_name,
            email=str(payload.email),
            phone=payload.phone,
            ownership_percentage=payload.ownership_percentage,
            persona_status="pending",
        )
        db.add(ubo)
        db.commit()
        db.refresh(ubo)
        logger.info(f"[onboarding/ubo/start] Created new UBO reference={ubo.ubo_reference_id}")

    return {
        "message": "UBO onboarding initialized",
        "reference_id": payload.reference_id,
        "ubo_reference_id": ubo.ubo_reference_id,
        "persona_template_id": settings.PERSONA_TEMPLATE_ID,
        "persona_environment": settings.PERSONA_ENVIRONMENT,
        "status": ubo.persona_status,
        "ownership_percentage": ubo.ownership_percentage,
    }


@app.post("/api/v1/onboarding/ubo/verify")
async def verify_ubo_onboarding(payload: UboVerifyRequest, db: Session = Depends(get_db)):
    """Verify UBO Persona inquiry and persist result."""
    logger.info(f"[onboarding/ubo/verify] ubo_reference_id={payload.ubo_reference_id}")

    ubo = db.query(models.UserKycUbo).filter(models.UserKycUbo.ubo_reference_id == payload.ubo_reference_id).first()
    if not ubo:
        logger.warning(f"[onboarding/ubo/verify] UBO not found for reference={payload.ubo_reference_id}")
        raise HTTPException(status_code=404, detail="UBO onboarding record not found")

    attrs = await _fetch_persona_inquiry_attributes(payload.inquiry_id, ubo.email, ubo.phone)
    persona_ref = attrs.get("referenceId")
    if persona_ref != ubo.ubo_reference_id:
        logger.warning(
            f"[onboarding/ubo/verify] reference mismatch expected={ubo.ubo_reference_id} actual={persona_ref}"
        )
        raise HTTPException(status_code=400, detail="Persona inquiry does not match this UBO")

    persona_status = attrs.get("status", "unknown")
    if persona_status not in ALLOWED_PERSONA_STATUSES:
        logger.warning(f"[onboarding/ubo/verify] status not eligible: {persona_status}")
        raise HTTPException(
            status_code=400,
            detail=f"UBO inquiry status is '{persona_status}', expected one of {sorted(ALLOWED_PERSONA_STATUSES)}",
        )

    ubo.persona_inquiry_id = payload.inquiry_id
    ubo.persona_status = persona_status
    ubo.verified_at = datetime.now()
    db.commit()
    db.refresh(ubo)

    return {
        "message": "UBO verification completed",
        "ubo_reference_id": ubo.ubo_reference_id,
        "status": ubo.persona_status,
        "persona_inquiry_id": ubo.persona_inquiry_id,
        "verified_at": ubo.verified_at.isoformat() if ubo.verified_at else None,
    }


@app.get("/api/v1/onboarding/ubo/status/{reference_id}")
async def get_ubo_status(reference_id: str, db: Session = Depends(get_db)):
    """Return all UBO statuses for an onboarding session."""
    logger.info(f"[onboarding/ubo/status] reference_id={reference_id}")
    kyc = db.query(models.UserKyc).filter(models.UserKyc.reference_id == reference_id).first()
    if not kyc:
        raise HTTPException(status_code=404, detail="Onboarding session not found")

    ubos = db.query(models.UserKycUbo).filter(models.UserKycUbo.kyc_id == kyc.id).all()
    ubo_items = [
        {
            "ubo_reference_id": ubo.ubo_reference_id,
            "full_name": ubo.full_name,
            "email": ubo.email,
            "phone": ubo.phone,
            "ownership_percentage": ubo.ownership_percentage,
            "status": ubo.persona_status,
            "persona_inquiry_id": ubo.persona_inquiry_id,
            "verified_at": ubo.verified_at.isoformat() if ubo.verified_at else None,
        }
        for ubo in ubos
    ]
    verified_count = len([u for u in ubos if u.persona_status in ALLOWED_PERSONA_STATUSES])

    return {
        "reference_id": reference_id,
        "ubo_count": len(ubo_items),
        "ubo_verified_count": verified_count,
        "ubos": ubo_items,
    }


@app.get("/api/v1/onboarding/status/{reference_id}")
async def get_onboarding_status(reference_id: str, db: Session = Depends(get_db)):
    """Check onboarding state by reference_id. No auth required."""
    logger.info(f"[onboarding/status] Request for reference_id={reference_id}")
    kyc = db.query(models.UserKyc).filter(models.UserKyc.reference_id == reference_id).first()
    if not kyc:
        logger.warning(f"[onboarding/status] Not found: reference_id={reference_id}")
        raise HTTPException(status_code=404, detail="Onboarding session not found")

    doc_fields = [
        "certificate_of_incorporation", "memorandum_and_articles",
        "ubos_schedule", "company_profile", "id_documents",
        "company_address_proof", "regulatory_information", "source_of_funds",
    ]
    documents = {f: getattr(kyc, f) for f in doc_fields if getattr(kyc, f)}
    ubos = db.query(models.UserKycUbo).filter(models.UserKycUbo.kyc_id == kyc.id).all()
    verified_ubos = [u for u in ubos if u.persona_status in ALLOWED_PERSONA_STATUSES]
    logger.info(f"[onboarding/status] Found: status={kyc.persona_status}, docs={len(documents)}, user_id={kyc.user_id}")

    return {
        "reference_id": kyc.reference_id,
        "status": kyc.persona_status,
        "persona_inquiry_id": kyc.persona_inquiry_id,
        "user_id": kyc.user_id,
        "verified_at": kyc.verified_at.isoformat() if kyc.verified_at else None,
        "documents_uploaded": len(documents),
        "documents": documents,
        "ubo_count": len(ubos),
        "ubo_verified_count": len(verified_ubos),
        "ubos": [
            {
                "ubo_reference_id": u.ubo_reference_id,
                "full_name": u.full_name,
                "email": u.email,
                "phone": u.phone,
                "ownership_percentage": u.ownership_percentage,
                "status": u.persona_status,
                "persona_inquiry_id": u.persona_inquiry_id,
                "verified_at": u.verified_at.isoformat() if u.verified_at else None,
            }
            for u in ubos
        ],
    }


# @app.post("/api/v1/onboarding/complete")
# async def complete_onboarding(
#     inquiry_id: Optional[str] = Form(None),
#     reference_id: Optional[str] = Form(None),
#     full_name: Optional[str] = Form(None),
#     company_name: Optional[str] = Form(None),
#     email: str = Form(...),
#     phone: str = Form(...),
#     certificate_of_incorporation: UploadFile = File(None),
#     memorandum_and_articles: UploadFile = File(None),
#     ubos_schedule: UploadFile = File(None),
#     company_profile: UploadFile = File(None),
#     id_documents: UploadFile = File(None),
#     company_address_proof: UploadFile = File(None),
#     regulatory_information: UploadFile = File(None),
#     source_of_funds: UploadFile = File(None),
#     db: Session = Depends(get_db),
# ):
#     """
#     Single submission for new users: Persona inquiry_id + contact info + documents.
#     No auth required — this creates the user account.
#     """
#     logger.info(
#         f"[onboarding/complete] Request received: inquiry_id={inquiry_id}, reference_id={reference_id}, email={email}, phone={phone}"
#     )

#     first_name = ""
#     last_name = ""
#     persona_status = "completed"
#     resolved_reference_id = reference_id

#     # 1. Verify the Persona inquiry server-side when one is provided.
#     if inquiry_id:
#         attrs = await _fetch_persona_inquiry_attributes(inquiry_id, email, phone)
#         resolved_reference_id = attrs.get("referenceId")
#         logger.info(
#             f"[onboarding/complete] Persona response: referenceId={resolved_reference_id}, status={attrs.get('status')}"
#         )

#         persona_status = attrs.get("status", "unknown")
#         if persona_status not in ALLOWED_PERSONA_STATUSES:
#             logger.warning(f"[onboarding/complete] Inquiry not eligible to continue: status={persona_status}")
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Inquiry status is '{persona_status}', expected one of {sorted(ALLOWED_PERSONA_STATUSES)}",
#             )

#         # Extract verified name from Persona when available.
#         first_name = attrs.get("nameFirst", "")
#         last_name = attrs.get("nameLast", "")
#         logger.info(f"[onboarding/complete] Persona verified name: {first_name} {last_name}")
#     elif not resolved_reference_id:
#         raise HTTPException(status_code=400, detail="Missing onboarding reference")
#     else:
#         logger.info(
#             f"[onboarding/complete] No Persona inquiry provided; defaulting persona_status={persona_status} for reference_id={resolved_reference_id}"
#         )

#     # 2. Find the KYC record by reference_id
#     kyc = db.query(models.UserKyc).filter(models.UserKyc.reference_id == resolved_reference_id).first()
#     if not kyc:
#         logger.error(f"[onboarding/complete] No KYC record for reference_id={resolved_reference_id}")
#         raise HTTPException(status_code=400, detail="No onboarding session found for this inquiry")

#     # TODO: Approve on prod.
#     # if kyc.user_id:
#     #     logger.warning(f"[onboarding/complete] Already completed: reference_id={reference_id}, user_id={kyc.user_id}")
#     #     raise HTTPException(status_code=409, detail="Onboarding already completed for this session")

#     ubos = db.query(models.UserKycUbo).filter(models.UserKycUbo.kyc_id == kyc.id).all()
#     if not ubos:
#         logger.warning(f"[onboarding/complete] No UBOs submitted for reference_id={reference_id}")
#         raise HTTPException(status_code=400, detail="At least one UBO must be added and verified")

#     unverified_ubos = [u for u in ubos if u.persona_status not in ALLOWED_PERSONA_STATUSES]
#     if unverified_ubos:
#         missing = ", ".join([u.full_name for u in unverified_ubos])
#         logger.warning(f"[onboarding/complete] Unverified UBOs: {missing}")
#         raise HTTPException(status_code=400, detail=f"These UBOs are not verified yet: {missing}")

#     # 4. Check if email is already registered
#     # existing = db.query(models.User).filter(models.User.email == email).first()
#     # if existing:
#     #     logger.warning(f"[onboarding/complete] Email already registered: {email}")
#     #     raise HTTPException(status_code=400, detail="Email already registered")

#     # 5. Create the user account
#     user_id = secrets.token_hex(8)
#     logger.info(f"[onboarding/complete] Creating user: user_id={user_id}, email={email}")


#     # 6. Read document bytes upfront (non-fatal)
#     files = {
#         "certificate_of_incorporation": certificate_of_incorporation,
#         "memorandum_and_articles": memorandum_and_articles,
#         "ubos_schedule": ubos_schedule,
#         "company_profile": company_profile,
#         "id_documents": id_documents,
#         "company_address_proof": company_address_proof,
#         "regulatory_information": regulatory_information,
#         "source_of_funds": source_of_funds,
#     }
#     provided = {k: v for k, v in files.items() if v is not None and v.filename}
#     logger.info(f"[onboarding/complete] Documents provided: {list(provided.keys())}")

#     urls: dict[str, str] = {}
#     file_bytes_cache: dict[str, tuple[str, bytes, str]] = {}
#     try:
#         for field_name, file in provided.items():
#             await file.seek(0)
#             raw = await file.read()
#             file_bytes_cache[field_name] = (file.filename, raw, file.content_type or "application/octet-stream")
#         logger.info(f"[onboarding/complete] Read {len(file_bytes_cache)} document(s) into memory")
#     except Exception as e:
#         logger.error(f"[onboarding/complete] Failed to read document bytes (non-fatal): {e}")

#     # 7. Link KYC record to the new user
#     # kyc.user_id = user_id
#     kyc.full_name = full_name
#     kyc.company_name = company_name
#     kyc.email = email
#     kyc.phone = phone
#     kyc.persona_inquiry_id = inquiry_id
#     kyc.persona_status = persona_status
#     kyc.verified_at = datetime.now()
#     for field, url in urls.items():
#         setattr(kyc, field, url)

#     existing_user = db.query(models.User).filter(models.User.email == email).first()
#     if existing_user:
#         existing_user.verified = True
#         if not existing_user.first_name and first_name:
#             existing_user.first_name = first_name
#         if not existing_user.last_name and last_name:
#             existing_user.last_name = last_name
#         if not existing_user.phone and phone:
#             existing_user.phone = phone

#     db.commit()
#     db.refresh(kyc)
#     logger.info(f"[onboarding/complete] KYC record linked to user_id={user_id}")

#     # 8. Send Slack notification with basic info (non-fatal)
#     try:
#         persona_inquiry_url = (
#             f"https://app.withpersona.com/dashboard/inquiries/{kyc.persona_inquiry_id}"
#             if kyc.persona_inquiry_id
#             else None
#         )

#         ubo_lines = "\\n".join([
#             f"- {u.full_name} ({u.persona_status}, ownership: {(f'{u.ownership_percentage:g}%' if u.ownership_percentage is not None else 'N/A')})"
#             for u in ubos
#         ])

#         persona_link_line = (
#             f"    Persona Inquiry Link: <{persona_inquiry_url}|Open Inquiry>\n"
#             if persona_inquiry_url
#             else ""
#         )

#         message = f"""*New Onboarding*
#     Full Name: {full_name or 'N/A'}
#     Company Name: {company_name or 'N/A'}
#     Email: {email}
#     Persona Inquiry Id: {inquiry_id or 'Not required'}
#     Phone: {phone}
#     Persona Status: {kyc.persona_status},
#     Persona Inquiry_id: {kyc.persona_inquiry_id or 'Not required'},
# {persona_link_line}    UBO Count: {len(ubos)},
#     Verified UBOs: {len([u for u in ubos if u.persona_status in ALLOWED_PERSONA_STATUSES])},
#     UBO List:\n{ubo_lines}
#     Documents: {len(file_bytes_cache)} file(s) — see compliance email"""

#         send_slack_message("onboarding", message)
#         logger.info(f"[onboarding/complete] Slack notification sent for {email}")
#     except Exception as e:
#         logger.error(f"[onboarding/complete] Failed to send Slack notification (non-fatal): {e}")

#     # 9. Email documents to compliance (non-fatal)
#     if file_bytes_cache:
#         try:
#             email_attachments = [
#                 {"filename": fname, "content": list(raw)}
#                 for fname, raw, _ in file_bytes_cache.values()
#             ]
#             doc_list_html = "".join(
#                 f"<li>{name.replace('_', ' ').title()}</li>"
#                 for name in file_bytes_cache
#             )
#             compliance_html = f"""
#                 <p>A new onboarding submission has been received.</p>
#                 <ul>
#                 <li><strong>Full Name:</strong> {full_name or 'N/A'}</li>
#                 <li><strong>Company Name:</strong> {company_name or 'N/A'}</li>
#                 <li><strong>Email:</strong> {email}</li>
#                 <li><strong>Phone:</strong> {phone or 'N/A'}</li>
#                 </ul>
#                 <p>Documents attached:</p>
#                 <ul>{doc_list_html}</ul>
#                 """
#             send_email(
#                 template=None,
#                 subject=f"New Onboarding Documents — {company_name or full_name or email}",
#                 to=["mr.adumatta@gmail.com"],
#                 context={},
#                 from_email="onboarding@noreply.vaulta.digital",
#                 attachments=email_attachments,
#                 html=compliance_html,
#             )
#             logger.info(f"[onboarding/complete] Compliance email sent for {email}")
#         except Exception as e:
#             logger.error(f"[onboarding/complete] Failed to send compliance email (non-fatal): {e}")

#     logger.info(f"[onboarding/complete] Onboarding complete for {email}, user_id={user_id}, docs={len(urls)}")
#     return {
#         "message": "Documents submitted successfully — pending review",
#         "reference_id": resolved_reference_id,
#         "email": email,
#         "persona_status": kyc.persona_status,
#         "persona_inquiry_id": kyc.persona_inquiry_id,
#         "documents_uploaded": len(urls),
#         "document_urls": urls,
#     }

# try:
    #     send_email(
    #         "welcome.html", "Welcome To Vaulta",
    #         to=[email],
    #         context={"name": new_user.first_name, "to": [email], "subject": "Welcome To Vaulta"},
    #     )
    #     logger.info(f"[onboarding/complete] Welcome email sent to {email}")
    # except Exception as e:
    #     logger.error(f"[onboarding/complete] Error sending welcome email: {e}")
    # Format a nice Slack message with document links
        
        
    # 4. Check if email is already registered
    # existing = db.query(models.User).filter(models.User.email == email).first()
    # if existing:
    #     logger.warning(f"[onboarding/complete] Email already registered: {email}")
    #     raise HTTPException(status_code=400, detail="Email already registered")

    # 5. Create the user account
    
@app.post("/api/v1/onboarding/complete")
async def complete_onboarding(
    inquiry_id: Optional[str] = Form(None),
    reference_id: Optional[str] = Form(None),
    full_name: Optional[str] = Form(None),
    company_name: Optional[str] = Form(None),
    email: str = Form(...),
    phone: str = Form(...),
    certificate_of_incorporation: Optional[str] = Form(None),
    memorandum_and_articles: Optional[str] = Form(None),
    ubos_schedule: Optional[str] = Form(None),
    company_profile: Optional[str] = Form(None),
    id_documents: Optional[str] = Form(None),
    company_address_proof: Optional[str] = Form(None),
    regulatory_information: Optional[str] = Form(None),
    source_of_funds: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Single submission for new users: Persona inquiry_id + contact info + documents.
    No auth required — this creates the user account.
    """
    logger.info(
        f"[onboarding/complete] Request received: inquiry_id={inquiry_id}, reference_id={reference_id}, email={email}, phone={phone}"
    )

    first_name = ""
    last_name = ""
    persona_status = "completed"
    resolved_reference_id = reference_id

    # 1. Verify the Persona inquiry server-side when one is provided.
    if inquiry_id:
        attrs = await _fetch_persona_inquiry_attributes(inquiry_id, email, phone)
        resolved_reference_id = attrs.get("referenceId")
        logger.info(
            f"[onboarding/complete] Persona response: referenceId={resolved_reference_id}, status={attrs.get('status')}"
        )

        persona_status = attrs.get("status", "unknown")
        if persona_status not in ALLOWED_PERSONA_STATUSES:
            logger.warning(f"[onboarding/complete] Inquiry not eligible to continue: status={persona_status}")
            raise HTTPException(
                status_code=400,
                detail=f"Inquiry status is '{persona_status}', expected one of {sorted(ALLOWED_PERSONA_STATUSES)}",
            )

        # Extract verified name from Persona when available.
        first_name = attrs.get("nameFirst", "")
        last_name = attrs.get("nameLast", "")
        logger.info(f"[onboarding/complete] Persona verified name: {first_name} {last_name}")
    elif not resolved_reference_id:
        raise HTTPException(status_code=400, detail="Missing onboarding reference")
    else:
        logger.info(
            f"[onboarding/complete] No Persona inquiry provided; defaulting persona_status={persona_status} for reference_id={resolved_reference_id}"
        )

    # 2. Find the KYC record by reference_id
    kyc = db.query(models.UserKyc).filter(models.UserKyc.reference_id == resolved_reference_id).first()
    if not kyc:
        logger.error(f"[onboarding/complete] No KYC record for reference_id={resolved_reference_id}")
        raise HTTPException(status_code=400, detail="No onboarding session found for this inquiry")

    # TODO: Approve on prod.
    # if kyc.user_id:
    #     logger.warning(f"[onboarding/complete] Already completed: reference_id={reference_id}, user_id={kyc.user_id}")
    #     raise HTTPException(status_code=409, detail="Onboarding already completed for this session")

    ubos = db.query(models.UserKycUbo).filter(models.UserKycUbo.kyc_id == kyc.id).all()
    if not ubos:
        logger.warning(f"[onboarding/complete] No UBOs submitted for reference_id={reference_id}")
        raise HTTPException(status_code=400, detail="At least one UBO must be added and verified")

    unverified_ubos = [u for u in ubos if u.persona_status not in ALLOWED_PERSONA_STATUSES]
    if unverified_ubos:
        missing = ", ".join([u.full_name for u in unverified_ubos])
        logger.warning(f"[onboarding/complete] Unverified UBOs: {missing}")
        raise HTTPException(status_code=400, detail=f"These UBOs are not verified yet: {missing}")
    user_id = secrets.token_hex(8)
    logger.info(f"[onboarding/complete] Creating user: user_id={user_id}, email={email}")
    # new_user = models.User(
    #     id=user_id,
    #     first_name=first_name or email.split("@")[0],
    #     last_name=last_name or "",
    #     email=email,
    #     phone=phone,
    # )
    # db.add(new_user)
    # db.flush()

    # 6. Collect Firebase document URLs (uploaded by the frontend)
    doc_fields = {
        "certificate_of_incorporation": certificate_of_incorporation,
        "memorandum_and_articles": memorandum_and_articles,
        "ubos_schedule": ubos_schedule,
        "company_profile": company_profile,
        "id_documents": id_documents,
        "company_address_proof": company_address_proof,
        "regulatory_information": regulatory_information,
        "source_of_funds": source_of_funds,
    }
    urls: dict[str, str] = {k: v for k, v in doc_fields.items() if v}
    logger.info(f"[onboarding/complete] Document URLs provided: {list(urls.keys())}")

    # 7. Link KYC record to the new user
    # kyc.user_id = user_id
    kyc.full_name = full_name
    kyc.company_name = company_name
    kyc.email = email
    kyc.phone = phone
    kyc.persona_inquiry_id = inquiry_id
    kyc.persona_status = persona_status
    kyc.verified_at = datetime.now()
    for field, url in urls.items():
        setattr(kyc, field, url)

    existing_user = db.query(models.User).filter(models.User.email == email).first()
    if existing_user:
        existing_user.verified = True
        if not existing_user.first_name and first_name:
            existing_user.first_name = first_name
        if not existing_user.last_name and last_name:
            existing_user.last_name = last_name
        if not existing_user.phone and phone:
            existing_user.phone = phone

    db.commit()
    db.refresh(kyc)
    # db.refresh(new_user)
    logger.info(f"[onboarding/complete] KYC record linked to user_id={user_id}")

    # 8. Send Slack notification with basic info (non-fatal)
    try:
        doc_links = "\n".join([f"    • <{url}|{name.replace('_', ' ').title()}>" for name, url in urls.items()]) if urls else "    • None"
        persona_inquiry_url = (
            f"https://app.withpersona.com/dashboard/inquiries/{kyc.persona_inquiry_id}"
            if kyc.persona_inquiry_id
            else None
        )

        ubo_lines = "\\n".join([
            f"- {u.full_name} ({u.persona_status}, ownership: {(f'{u.ownership_percentage:g}%' if u.ownership_percentage is not None else 'N/A')})"
            for u in ubos
        ])

        persona_link_line = (
            f"    Persona Inquiry Link: <{persona_inquiry_url}|Open Inquiry>\n"
            if persona_inquiry_url
            else ""
        )

        message = f"""*New Onboarding*
    Full Name: {full_name or 'N/A'}
    Company Name: {company_name or 'N/A'}
    Email: {email}
    Persona Inquiry Id: {inquiry_id or 'Not required'}
    Phone: {phone}
    Persona Status: {kyc.persona_status},
    Persona Inquiry_id: {kyc.persona_inquiry_id or 'Not required'},
{persona_link_line}    UBO Count: {len(ubos)},
    Verified UBOs: {len([u for u in ubos if u.persona_status in ALLOWED_PERSONA_STATUSES])},
    UBO List:\n{ubo_lines}
    Documents ({len(urls)}):\n{doc_links}"""

        send_slack_message("onboarding", message)
        logger.info(f"[onboarding/complete] Slack notification sent for {email}")
    except Exception as e:
        logger.error(f"[onboarding/complete] Failed to send Slack notification (non-fatal): {e}")

    # 9. Email document links to compliance (non-fatal)
    if urls:
        try:
            doc_list_html = "".join(
                f'<li><a href="{url}">{name.replace("_", " ").title()}</a></li>'
                for name, url in urls.items()
            )
            compliance_html = f"""
<p>A new onboarding submission has been received.</p>
<ul>
  <li><strong>Full Name:</strong> {full_name or 'N/A'}</li>
  <li><strong>Company Name:</strong> {company_name or 'N/A'}</li>
  <li><strong>Email:</strong> {email}</li>
  <li><strong>Phone:</strong> {phone or 'N/A'}</li>
</ul>
<p>Documents:</p>
<ul>{doc_list_html}</ul>
"""
            send_email(
                template=None,
                subject=f"New Onboarding Documents — {company_name or full_name or email}",
                to=["compliance@vaulta.digital"],
                context={},
                from_email="onboarding@noreply.vaulta.digital",
                html=compliance_html,
            )
            logger.info(f"[onboarding/complete] Compliance email sent for {email}")
        except Exception as e:
            logger.error(f"[onboarding/complete] Failed to send compliance email (non-fatal): {e}")

    logger.info(f"[onboarding/complete] Onboarding complete for {email}, user_id={user_id}, docs={len(urls)}")
    return {
        "message": "Documents submitted successfully — pending review",
        "reference_id": resolved_reference_id,
        "email": email,
        "persona_status": kyc.persona_status,
        "persona_inquiry_id": kyc.persona_inquiry_id,
        "documents_uploaded": len(urls),
        "document_urls": urls,
    }


@app.get("/")
async def root():
    return {"message":"Hello!"}

@app.post("/api/v1/get_quote")
async def create_quote_route(data: QuoteRequest, db:Session = Depends(get_db)):
    
    # USDT -> GHS = SELL
    # GHS -> USDT = BUY
    
    print("==data==")
    print(data)
    
    response = create_quote(data.model_dump())
    
    print("==response==")
    print(response)
    
    if isinstance(response, tuple) and len(response) == 2 and isinstance(response[1], int):
        # This is an error response
        raise HTTPException(status_code=response[1], detail=response[0])
    
    return response

# @app.get("/api/v1/pairs")
# async def get_markets_route():
#     markets = get_markets()
#     filtered_markets = [m['name'].replace("/","-") for m in markets]
#     return {"markets": filtered_markets}
    
SUPPORTED_PAIRS = ["USDC-GHS", "GHS-USDC", "USDC-USDT"]

@app.get("/api/v1/pairs")
async def get_markets_route():
    return {"markets": SUPPORTED_PAIRS}

@app.get("/api/v1/cron_rates")
async def get_todays_cron_rates():
    pair = "USDT-GHS" 
    side = "sell"
    
    quote = create_quote(
        {
            "pair": pair,
            "side": side,
            "amount_crypto": 0.001
        }
    )
    
    print(quote)
    message = f"{datetime.now().strftime('%c')}\nSIDE: {side}\n{pair}: {quote['price']}"
    send_private_slack(message)
    return quote        

class ApiKeyResponse(BaseModel):
    api_key: str
    expires_at: datetime

@app.post("/api/v1/create_api_key", response_model=ApiKeyResponse)
async def create_api_key(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Generate a new API key
    api_key = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=30)

    # Store API key in DB (assuming models.ApiKey exists)
    api_key_obj = models.ApiKey(
        key=api_key,
        user_id=user_id,
        expires_at=expires_at
    )
    db.add(api_key_obj)
    db.commit()
    db.refresh(api_key_obj)

    return ApiKeyResponse(api_key=api_key, expires_at=expires_at)

@app.get("/api/v1/api_keys")
async def get_api_keys(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    api_keys = db.query(models.ApiKey).filter(models.ApiKey.user_id == user_id).all()
    result = [
        {
            "api_key": key.key,
            "expires_at": key.expires_at,
            "active": key.is_active
        }
        for key in api_keys
    ]
    return {"api_keys": result}


@app.delete("/api/v1/delete_api_key/{api_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(api_key: str, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    api_key_obj = db.query(models.ApiKey).filter(models.ApiKey.key == api_key, models.ApiKey.user_id == user_id).first()
    if not api_key_obj:
        raise HTTPException(status_code=404, detail="API key not found")

    db.delete(api_key_obj)
    db.commit()
    return

class ToggleApiKeyRequest(BaseModel):
    api_key: str
    active: bool

@app.post("/api/v1/toggle_api_key")
async def toggle_api_key_status(body: ToggleApiKeyRequest, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    api_key_obj = db.query(models.ApiKey).filter(models.ApiKey.key == body.api_key, models.ApiKey.user_id == user_id).first()
    if not api_key_obj:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key_obj.active = body.active
    db.commit()
    db.refresh(api_key_obj)
    return {"api_key": api_key_obj.key, "active": api_key_obj.active}


@app.get("/api/v1/transactions")
async def get_all_transactions(user_id: str = Depends(get_authenticated_user_id), db: Session = Depends(get_db)):
    # transactions = db.query(models.Transaction).filter(models.Transaction.user_id == user_id).all()
    transactions = db.query(models.Transaction).all()
    pending_payments = db.query(models.Payment).filter(models.Payment.status == "pending").all()
    result = [
        {
            "id": str(tx.id),
            "amount": tx.amount,
            "currency": tx.currency,
            "type": tx.transaction_type,
            "provider": tx.provider,
            "status": tx.status,
            "reference": tx.reference,
            "description": tx.description,
            "created_at": tx.created_at,
            "updated_at": tx.updated_at
        }
        for tx in transactions
    ]
    
    payemnts = [
        {
            "id": str(payment.id),
            "amount": payment.amount,
            "currency": payment.currency,
            "type": "intent",
            "destination_rail": payment.destination_rail,
            "destination_network": payment.destination_network,
            "destination_address": payment.destination_address,
            "description": payment.description,
            "client_reference": payment.client_reference,
            "status": payment.status,
            "created_at": payment.created_at,
            "updated_at": payment.updated_at
        }
        for payment in pending_payments
    ]
    
    result.extend(payemnts)
    
    return result

@app.get("/api/v1/transactions/{transaction_id}")
async def get_transaction(
    transaction_id: str,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    transaction = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.user_id == user_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {
        "id": str(transaction.id),
        "amount": transaction.amount,
        "currency": transaction.currency,
        "type": transaction.transaction_type,
        "provider": transaction.provider,
        "status": transaction.status,
        "reference": transaction.reference,
        "description": transaction.description,
        "created_at": transaction.created_at,
        "updated_at": transaction.updated_at
    }

class CreateTransactionRequest(BaseModel):
    amount: float
    currency: str
    type: str  # e.g. "deposit", "withdrawal"
    status: Optional[str] = "pending"

@app.post("/api/v1/create_transactions", status_code=status.HTTP_201_CREATED)
async def create_transaction(
    data: CreateTransactionRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    transaction = models.Transaction(
        user_id=user_id,
        amount=data.amount,
        currency=data.currency,
        type=data.type,
        status=data.status,
        created_at=datetime.now()
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return {
        "id": str(transaction.id),
        "amount": transaction.amount,
        "currency": transaction.currency,
        "type": transaction.type,
        "status": transaction.status,
        "created_at": transaction.created_at
    }

@app.delete("/api/v1/transactions/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: str,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    transaction = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.user_id == user_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    db.delete(transaction)
    db.commit()
    return

class CreateAccountRequest(BaseModel):
    name: str
    currency: str
    metadata: Optional[dict] = None

class AccountResponse(BaseModel):
    id: str
    name: str
    currency: str
    status: str
    balances: dict
    metadata: Optional[dict] = None

class PaymentDestination(BaseModel):
    rail: str  # e.g., "stablecoin"
    network: str  # e.g., "solana" 
    address: str  # e.g., "6oK8...abc"

class CreatePaymentRequest(BaseModel):
    source_account_id: str
    amount: str
    currency: str
    destination: PaymentDestination
    description: Optional[str] = None
    client_reference: Optional[str] = None

class PaymentFee(BaseModel):
    type: str
    amount: str
    currency: str

class PaymentResponse(BaseModel):
    id: str
    status: str
    amount: str
    currency: str
    fx: Optional[dict] = None
    fees: List[PaymentFee]
    created_at: str

@app.post("/api/v1/create_account", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    data: CreateAccountRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        print("user_id")
        print(user_id)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalidated token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    account_id = secrets.token_hex(8)
    account_number = services.generate_account_number()
    account = models.Account(
        user_id=user_id,
        account_name=data.name,
        account_number=account_number,
        currency=data.currency,
        metadata=data.metadata or {}
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return AccountResponse(
        id=str(account.id),
        name=account.account_name,
        currency=account.currency,
        status=account.status,
        balances=account.balances or {},
        metadata=account.account_metadata
    )

@app.get("/api/v1/accounts", response_model=List[AccountResponse])
async def get_all_accounts(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    accounts = db.query(models.Account).filter(
        models.Account.user_id == user_id,
        models.Account.status == "ACTIVE"
    ).all()
    result = [
        AccountResponse(
            id=str(account.id),
            name=account.account_name,
            currency=account.currency,
            status=account.status,
            balances=account.balances or {},
            metadata=account.account_metadata
        )
        for account in accounts
    ]
    return result

@app.delete("/api/v1/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: str,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    account = db.query(models.Account).filter(
        models.Account.id == account_id,
        models.Account.user_id == user_id
    ).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.status = "DELETED"
    db.commit()
    # Return all accounts for the user after deletion
    accounts = db.query(models.Account).filter(
        models.Account.user_id == user_id,
        models.Account.status == "ACTIVE"
    ).all()
    result = [
        AccountResponse(
            id=str(account.id),
            name=account.account_name,
            currency=account.currency,
            status=account.status,
            balances=account.balances or {},
            metadata=account.account_metadata
        )
        for account in accounts
    ]
    return result

@app.put("/api/v1/accounts/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str,
    data: CreateAccountRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
    ):
    
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    account = db.query(models.Account).filter(
        models.Account.id == account_id,
        models.Account.user_id == user_id,
        models.Account.status == "ACTIVE"
    ).first()
    
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    account.account_name = data.name
    account.currency = data.currency
    # account.account_metadata = data.metadata or {}
    db.commit()
    db.refresh(account)
    
    return AccountResponse(
        id=str(account.id),
        name=account.account_name,
        currency=account.currency,
        status=account.status,
        balances=account.balances or {},
        metadata=account.account_metadata
    )
@app.post("/api/v1/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def create_payment(
    data: CreatePaymentRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
    ):
    
    BASE_URL="https://dashboard.vaulta.digital"
    logger_payments.info(f"[create_payment] Payment request received: {data.amount} {data.currency}")
    
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        logger_payments.info(f"[create_payment] User authenticated: {user_id}")
        
        if not user_id:
            logger_payments.warning(f"[create_payment] Invalid token: user_id missing")
            raise HTTPException(status_code=401, detail="Invalid token")
        
    except jwt.PyJWTError as e:
        logger_payments.error(f"[create_payment] JWT decode error: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

    source_account = db.query(models.Account).filter(
        models.Account.id == data.source_account_id,
        models.Account.user_id == user_id,
        models.Account.status == "ACTIVE"
    ).first()
    
    if not source_account:
        logger_payments.warning(f"[create_payment] Source account not found: {data.source_account_id}")
        raise HTTPException(status_code=404, detail="Source account not found")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        logger_payments.error(f"[create_payment] User not found: {user_id}")
        raise HTTPException(status_code=404, detail="User not found")

    payment_id = f"pay_{uuid.uuid4().hex[:8].upper()}"
    logger_payments.info(f"[create_payment] Generated payment ID: {payment_id}")
    
    network_fee = PaymentFee(
        type="network",
        amount="0.12",
        currency=data.currency
    )
    
    logger_payments.info(f"[create_payment] Creating payment record: {payment_id}")
    payment = models.Payment(
        id=payment_id,
        user_id=user_id,
        source_account_id=data.source_account_id,
        amount=data.amount,
        currency=data.currency,
        destination_rail=data.destination.rail,
        destination_network=data.destination.network,
        destination_address=data.destination.address,
        description=data.description,
        client_reference=data.client_reference,
        status="pending",
        fx_data=None,  # No FX for same currency
        fees_data=json.dumps([network_fee.model_dump()])
    )
    
    db.add(payment)
    db.commit()
    db.refresh(payment)
    
    logger_payments.info(f"[create_payment] Payment record created and saved")
    
    try:
        send_email(
            template="payment_created.html",
            subject="Your payment request has been received",
            to=[user.email],
            context={
                "name": user.first_name,
                "amount": data.amount,
                "currency": data.currency,
                "source_account_id": source_account.id,
                "destination_rail": data.destination.rail,
                "destination_network": data.destination.network,
                "destination_address": data.destination.address,
                "description": data.description,
                "client_reference": data.client_reference,
                "payment_id": payment_id,
            }
        )
        logger_payments.info(f"[create_payment] User notification email sent to {user.email}")
    except Exception as e:
        logger_payments.error(f"[create_payment] Failed to send payment creation email: {e}")
        send_slack_message("rates", f"⚠️ Payment {payment_id}: Failed to send email to {user.email}")
        
    try:
        send_email(
        template="transaction_approval_required.html",
        subject=f"[DEMO] Approval required: Transaction {payment_id}",
        to=["dev@vaulta.digital"],
        context={
            "payment_id": payment_id,
            "initiator_name": user.first_name,
            "initiator_email": user.email,
            "amount": data.amount,
            "currency": data.currency,
            "source_account_id": source_account.id,
            "destination_rail": data.destination.rail,
            "destination_network": data.destination.network,
            "destination_address": data.destination.address,
            "description": data.description,
            "client_reference": data.client_reference,
            "approve_url": f"{BASE_URL}/dashboard",
            "decline_url": f"{BASE_URL}/dashboard",
        },
        from_email="payments@noreply.vaulta.digital"
        )
        logger_payments.info(f"[create_payment] Admin approval email sent for {payment_id}")
    except Exception as e:
        logger_payments.error(f"[create_payment] Failed to send admin approval email: {e}")
        send_slack_message("rates", f"⚠️ Payment {payment_id}: Failed to send admin approval email")
    
    response = PaymentResponse(
        id=payment.id,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        fx=None,
        fees=[network_fee],
        created_at=payment.created_at.isoformat() + "Z"
    )
    
    logger_payments.info(f"[create_payment] Payment creation complete: {payment_id}")
    return response

@app.get("/api/v1/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: str,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    payment = db.query(models.Payment).filter(
        models.Payment.id == payment_id,
        models.Payment.user_id == user_id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Parse fees_data from JSON
    fees = []
    if payment.fees_data:
        try:
            fees_list = json.loads(payment.fees_data)
            fees = [PaymentFee(**fee) for fee in fees_list]
        except Exception:
            fees = []

    return PaymentResponse(
        id=payment.id,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        fx=payment.fx_data if payment.fx_data else None,
        fees=fees,
        created_at=payment.created_at.isoformat() + "Z"
    )

class UpdateTransactionRequest(BaseModel):
    amount: Optional[float] = None
    currency: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None

class ApprovePaymentRequest(BaseModel):
    admin_id: str
    approved: bool
    reason: Optional[str] = None

@app.post("/api/v1/payments/{payment_id}/approve", response_model=PaymentResponse)
async def approve_payment(
    payment_id: str,
    data: ApprovePaymentRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to approve or reject a payment.
    When approved, creates a corresponding transaction.
    """
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        admin_user_id = payload.get("sub")
        if not admin_user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # TODO: Add admin role check here
    # if not is_admin(admin_user_id):
    #     raise HTTPException(status_code=403, detail="Admin access required")

    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.status != "pending":
        raise HTTPException(status_code=400, detail="Payment is not in pending status")

    if data.approved:
        # Create corresponding transaction when payment is approved
        transaction = models.Transaction(
            amount=int(float(payment.amount) * 100),  # Convert to cents
            currency=payment.currency,
            user_id=payment.user_id,
            transaction_type="payment",
            provider="stablecoin",
            status="completed",
            reference=payment.client_reference,
            description=payment.description
        )
        db.add(transaction)
        db.flush()  # Get the transaction ID

        # Update payment with transaction reference and approval info
        payment.transaction_id = transaction.id
        payment.status = "approved"
        payment.admin_approved_by = data.admin_id
        payment.admin_approved_at = datetime.now()
    else:
        # Reject the payment
        payment.status = "rejected"
        payment.admin_approved_by = data.admin_id
        payment.admin_approved_at = datetime.now()

    db.commit()
    db.refresh(payment)

    # Parse fees_data from JSON
    fees = []
    if payment.fees_data:
        try:
            fees_list = json.loads(payment.fees_data)
            fees = [PaymentFee(**fee) for fee in fees_list]
        except Exception:
            fees = []

    return PaymentResponse(
        id=payment.id,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        fx=payment.fx_data if payment.fx_data else None,
        fees=fees,
        created_at=payment.created_at.isoformat() + "Z"
    )

@app.get("/api/v1/admin/payments/pending")
async def get_pending_payments(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Admin endpoint to get all pending payments for approval.
    """
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        admin_user_id = payload.get("sub")
        if not admin_user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # TODO: Add admin role check here
    # if not is_admin(admin_user_id):
    #     raise HTTPException(status_code=403, detail="Admin access required")

    pending_payments = db.query(models.Payment).filter(
        models.Payment.status == "pending"
    ).all()

    result = []
    for payment in pending_payments:
        # Get user info
        user = db.query(models.User).filter(models.User.id == payment.user_id).first()
        
        # Parse fees
        fees = []
        if payment.fees_data:
            try:
                fees_list = json.loads(payment.fees_data)
                fees = [PaymentFee(**fee) for fee in fees_list]
            except Exception:
                fees = []

        result.append({
            "id": payment.id,
            "user": {
                "id": payment.user_id,
                "name": f"{user.first_name} {user.last_name}" if user else "Unknown",
                "email": user.email if user else "Unknown"
            },
            "amount": payment.amount,
            "currency": payment.currency,
            "destination": {
                "rail": payment.destination_rail,
                "network": payment.destination_network,
                "address": payment.destination_address
            },
            "description": payment.description,
            "client_reference": payment.client_reference,
            "fees": [fee.model_dump() for fee in fees],
            "created_at": payment.created_at.isoformat() + "Z"
        })

    return {"pending_payments": result, "count": len(result)}

@app.get("/api/v1/payments/{payment_id}/transaction")
async def get_payment_transaction(
    payment_id: str,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Get the transaction associated with a payment.
    """
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    payment = db.query(models.Payment).filter(
        models.Payment.id == payment_id,
        models.Payment.user_id == user_id
    ).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if not payment.transaction_id:
        return {"message": "No transaction associated with this payment yet"}

    transaction = db.query(models.Transaction).filter(
        models.Transaction.id == payment.transaction_id
    ).first()
    
    if not transaction:
        raise HTTPException(status_code=404, detail="Associated transaction not found")

    return {
        "transaction_id": str(transaction.id),
        "amount": transaction.amount,
        "currency": transaction.currency,
        "type": transaction.transaction_type,
        "provider": transaction.provider,
        "status": transaction.status,
        "reference": transaction.reference,
        "description": transaction.description,
        "created_at": transaction.created_at,
        "updated_at": transaction.updated_at
    }

@app.put("/api/v1/transactions/{transaction_id}", status_code=status.HTTP_200_OK)
async def update_transaction(
    transaction_id: str,
    data: UpdateTransactionRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    transaction = db.query(models.Transaction).filter(
        models.Transaction.id == transaction_id,
        models.Transaction.user_id == user_id
    ).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")

    if data.amount is not None:
        transaction.amount = data.amount
    if data.currency is not None:
        transaction.currency = data.currency
    if data.type is not None:
        transaction.type = data.type
    if data.status is not None:
        transaction.status = data.status

    db.commit()
    db.refresh(transaction)
    return {
        "id": str(transaction.id),
        "amount": transaction.amount,
        "currency": transaction.currency,
        "type": transaction.type,
        "status": transaction.status,
        "created_at": transaction.created_at
    }
    
    
@app.post("/api/v1/transaction", status_code=status.HTTP_201_CREATED)
async def create_single_transaction(
    data: CreateTransactionRequest,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    transaction = models.Transaction(
        user_id=user_id,
        amount=data.amount,
        currency=data.currency,
        type=data.type,
        status=data.status,
        created_at=datetime.now()
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return {
        "id": str(transaction.id),
        "amount": transaction.amount,
        "currency": transaction.currency,
        "type": transaction.type,
        "status": transaction.status,
        "created_at": transaction.created_at
    }



@app.get("/api/v1/admin/transactions")
async def get_all_admin_transactions(user_id: str = Depends(get_authenticated_user_id), db: Session = Depends(get_db)):
    # transactions = db.query(models.Transaction).filter(models.Transaction.user_id == user_id).all()
    transactions = db.query(models.Transaction).all()
    result = [
        {
            "id": str(tx.id),
            "amount": tx.amount,
            "currency": tx.currency,
            "type": tx.transaction_type,
            "provider": tx.provider,
            "status": tx.status,
            "reference": tx.reference,
            "description": tx.description,
            "created_at": tx.created_at,
            "updated_at": tx.updated_at
        }
        for tx in transactions
    ]
    return result


@app.get("/api/v1/admin/users")
async def get_all_users(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    users = db.query(models.User).all()
    result = [
        {
            "id": str(user.id),
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "phone": user.phone
        }
        for user in users
    ]
    return {"data": result, "count": len(result)}


@app.get("/api/v1/fx_rates")
async def get_all_fx_rates(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    fx_rates = db.query(models.FxRates).all()
    result = [
        {
            "id": str(fx_rate.id),
            "pair": fx_rate.pair,
            "buy": fx_rate.buy,
            "sell": fx_rate.sell,
            "buy_price": fx_rate.buy_price,
            "sell_price": fx_rate.sell_price
        }
        for fx_rate in fx_rates
    ]
    return {"data": result, "count": len(result)}


# response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
# async def create_payment(
#     data: CreatePaymentRequest,

# 

class FxRatesUpdateRequest(BaseModel):
    pair: str
    buy: str
    sell: str
    

class FxRatesUpdateResponse(BaseModel):
    pair: str
    buy: str
    sell: str

@app.post("/api/v1/fx_rates")
async def get_all_fx_rates(data:FxRatesUpdateRequest, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    fxrates_id = f"pay_{uuid.uuid4().hex[:8].upper()}"
    print("Generated payment ID:", fxrates_id)
    
    new_fx_rate = models.FxRates(
        id = fxrates_id,
        pair = data.pair,
        buy = data.buy,
        sell = data.sell,
        sell_price = data.sell,
        buy_price = data.sell
    )
    
    db.add(new_fx_rate)
    db.commit()
    db.refresh(new_fx_rate)
    
    return new_fx_rate

@app.get("/api/v1/ovex/history")
async def get_trade_history_route(
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    token: str = Depends(oauth2_scheme), 
    db: Session = Depends(get_db)
    ):
    print("===")
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Assuming you have a TradeHistory model/table
    # Parse start_date and end_date from query parameters
    request: Request = db  # db is actually the Depends(get_db), so get from context
    # But FastAPI doesn't inject Request here, so let's use Query parameters in the route signature instead.
    # So, update your route definition to:
    # async def get_trade_history_route(
    #     start_date: Optional[str] = Query(None),
    #     end_date: Optional[str] = Query(None),
    #     token: str = Depends(oauth2_scheme),
    #     db: Session = Depends(get_db)
    # ):

    # For now, try to get from request.query_params if possible (but best to update route signature)
    # frame = inspect.currentframe()
    # args, _, _, values = inspect.getargvalues(frame)
    # start_date = values.get('from', None)
    # end_date = values.get('to', None)

    # If not present, fallback to None
    if not start_date:
        start_date = None
    if not end_date:
        end_date = None

    # Call get_trade_history with date filters if provided
    trades = get_trade_history(start_date=start_date, end_date=end_date)['trades']
    
    print(trades[0])
    result = [
        {
            "id": str(trade['id']),
            "from_currency": trade['from_currency'],
            "to_currency": trade['to_currency'],
            "from_amount": trade['from_amount'],
            "to_amount": trade['to_amount'],
            "rate": trade['rate'],
            "status": trade['status'],
            "created_at": trade['created_at']
        }
        for trade in trades
    ]
    
    total_from_amount = sum(float(trade['from_amount']) for trade in trades)
    total_to_amount = sum(float(trade['to_amount']) for trade in trades)
    
    
    return {"trade_history": result, "count": len(result), 
            "total_from_amount": total_from_amount,
            "total_to_amount": total_to_amount,}

@app.get("/api/v1/ovex/total")
async def get_trade_total_route(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    trades = get_trade_history()['trades']
     
    total_from_amount = sum(float(trade['from_amount']) for trade in trades)
    total_to_amount = sum(float(trade['to_amount']) for trade in trades)
    return {
        "total_from_amount": total_from_amount,
        "total_to_amount": total_to_amount,
        "count": len(trades)
    }
    
@app.post("/api/v1/notify")
async def notify_slack(data: dict = Body(...)):
    # Extract headers and query parameters
    headers = dict(request.headers) if hasattr(request, 'headers') else {}
    
    params = dict(request.query_params) if hasattr(request, 'query_params') else {}

    # Log the incoming notification with headers and params
    message = f"Received notification with headers: {headers}\nNotification data: {data}\nParams: {params}"
    print(message)
    
    try:
        send_slack_message("rates",f"UNROUTED NOTIFICATION: {message}")
        return {"message": "Notification sent to Slack", "data": message}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send notification: {str(e)}")
