import os
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from typing import Dict, List, Annotated, Optional
import secrets
import random
from datetime import datetime, timedelta

from authstore import save_access_token, save_user_otp


import resend
import authstore
from database import engine, SessionLocal
import models
from sqlalchemy.orm import Session


from services import get_customer_by_email, issue_jwt_token, send_otp_to_email_for_login
from utils import generate_otp, send_email
from fastapi import Body
import hashlib
import jwt
from fastapi.security import OAuth2PasswordBearer

app = FastAPI()



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
        return JSONResponse(
        status_code=404,
        content={"message": "User was not found"}
    )
        # return ApiResponse(message = "User was not found", code=404, data={}, status="Failed"), 404
    
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
    
    print("OTP verification successful")
    # return {"message": "OTP verified", "user_id": user_id}
    return jwt_response

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

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
        "phone": user.phone
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
        "phone": new_customer.phone
    }

@app.get("/")
async def root():
    return {"message":"Hello!"}
