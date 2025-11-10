import os
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
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
from utils import generate_otp, send_email, send_slack, send_private_slack
from fastapi import Body
import hashlib
import jwt
from fastapi.security import OAuth2PasswordBearer

from ovex_apis import create_quote
from ovex_apis import get_markets
from redis_client import r

app = FastAPI()

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
    
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.post("/login", response_model=ApiResponse, status_code=status.HTTP_200_OK)
async def login(user_data: UserLogin, db: Session = Depends(get_db)):
    # In a real application, you would:
    # 1. Retrieve the user from a database
    # 2. Verify the password using a secure hashing algorithm
    # 3. Generate a proper JWT token
    
    print("Starting login process...")
    
    email = user_data.email
    print("email")
    print(email)
    print(f"Attempting login for email: {email}")
    
    print("Fetching user from database...")
    user = get_customer_by_email(email, db)
    print(f"User found: {user is not None}")
    
    if not user:
        print("User not found in database")
        send_private_slack(f"EMAIL: {user.email} was not found")
        return JSONResponse(
        status_code=404,
        content={"message": "User was not found"}
    )
    
    print("Sending OTP email...")
    # email_response = send_otp_to_email_for_login(user, db)
    
    otp = generate_otp()
    to = [user.email]
    
    # hash the otp
    # hashed_otp = hashlib.sha256(otp.encode()).hexdigest()
    
    # update user body with password
    user.password = otp
    db.commit()
    db.refresh(user)
    
    send_email("otp.html", f"OTP - {otp}", to, {"name":user.first_name, "otp":otp})
    print("email_response")
    
    send_private_slack(f"Login attempt for email: {email} OTP: {otp}")

    
    print("Generating token...")
    # Generate a token (use a proper JWT in production)
    
    token = secrets.token_hex(32)
    print(f"Token generated: {token[:10]}...")
    
    save_access_token(token, str(user.id))
    
    save_user_otp(str(user.id),otp)  
    
    print("Login process completed successfully")
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
    # 1) Get token from header
    print(f"Received token: {body.token}")
    token = body.token
    if not token:
        print("Missing or invalid Authorization header")
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    # 2) Lookup user_id in Redis
    user_id = authstore.get_user_id_from_token(token)
    print(f"User ID from token: {user_id}")
    
    user = authstore.get_user_by_id(user_id)
    print("===user===")
    print(user)
    
    if not user_id:
        print("Invalid or expired access token")
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    # 3) Fetch expected OTP (from Redis or DB)
    expected_otp = authstore.get_user_otp(user_id)
    print("Expected OTP: ", expected_otp)
    
    # decode the hashed password
    if expected_otp:
        provided_otp = "123456"
        provided_hashed = hashlib.sha256(provided_otp.encode()).hexdigest()
        print("Provided Hash:", provided_hashed)
    # If stored in Redis:
    # expected_otp = user.otp
    # If stored in DB instead:
    
    # if you stored it in Redis
    print(f"Expected OTP for user {user_id}: {expected_otp}")
    # If stored in DB instead:
    # user = db.query(models.User).get(user_id)
    # expected_otp = user.verification_token

    if not expected_otp or body.otp != expected_otp:
        print(f"Invalid OTP. Provided: {body.otp}, Expected: {expected_otp}")
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # 4) Success: clear OTP, optionally rotate the token or upgrade session
    print(f"OTP verified for user {user_id}. Clearing OTP...")
    authstore.clear_user_otp(user_id)
    
    # Optionally: issue a longer-lived JWT here and/or revoke the short-lived token.
    # JWT settings
    jwt_response = issue_jwt_token(user_id)
    print("==jwt_response==")
    print(jwt_response)
    
    jwt_response['user'] = user

    print("OTP verification successful")
    # return {"message": "OTP verified", "user_id": user_id}
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
    print("Decoding JWT token...")
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        print("JWT payload:", payload)
        user_id = payload.get("sub")
        print("Extracted user_id from token:", user_id)
        if not user_id:
            print("Invalid token: user_id missing")
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError as e:
        print("JWT decode error:", str(e))
        raise HTTPException(status_code=401, detail="Invalid token")

    print("Querying user from database with user_id:", user_id)
    user = db.query(models.User).filter(models.User.id == user_id).first()
    
    if not user:
        print("User not found for user_id:", user_id)
        raise HTTPException(status_code=404, detail="User not found")
    print("User found:", user)
    
    return {
        "id": str(user.id),
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
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
    
    # Check if email already exists
    print("Checking if email exists:", user_data.email)
    # if user_data.email in users_db:
        
    existing = db.query(models.User).filter(models.User.email == user_data.email).first()
    if existing:
        print("Email already registered")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    user_id = secrets.token_hex(8)
    print("Generated user ID:", user_id)
    
    new_customer = models.User(
        id = user_id,
        first_name = user_data.first_name,
        last_name = user_data.last_name,
        email = user_data.email,
        phone = user_data.phone,
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

@app.get("/api/v1/pairs")
async def get_markets_route():
    markets = get_markets()
    filtered_markets = [m['name'].replace("/","-") for m in markets]
    return {"markets": filtered_markets}
    
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

@app.get("/api/v1/transactions")
async def get_all_transactions(user_id: str = Depends(get_authenticated_user_id), db: Session = Depends(get_db)):
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
    
    """
    Create a new payment to a stablecoin address.
    """
    
    print("Received payment request data:", data)
    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        print("Decoded JWT payload:", payload)
        
        if not user_id:
            print("Invalid token: user_id missing")
            raise HTTPException(status_code=401, detail="Invalid token")
        
    except jwt.PyJWTError as e:
        print("JWT decode error:", str(e))
        raise HTTPException(status_code=401, detail="Invalid token")

    print("Verifying source account...")
    source_account = db.query(models.Account).filter(
        models.Account.id == data.source_account_id,
        models.Account.user_id == user_id,
        models.Account.status == "ACTIVE"
    ).first()
    
    if not source_account:
        print("Source account not found for user:", user_id)
        raise HTTPException(status_code=404, detail="Source account not found")

    payment_id = f"pay_{uuid.uuid4().hex[:8].upper()}"
    print("Generated payment ID:", payment_id)
    
    network_fee = PaymentFee(
        type="network",
        amount="0.12", #TODO: UPDATE WITH OUR FX RATE
        currency=data.currency
    )
    
    print("Calculated network fee:", network_fee)
    
    print("Creating payment record in database...")
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
    
    print("Payment record created:", payment)
    
    response = PaymentResponse(
        id=payment.id,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        fx=None,
        fees=[network_fee],
        created_at=payment.created_at.isoformat() + "Z"
    )
    
    print("Returning payment response:", response)
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
