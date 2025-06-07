from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Annotated, Optional
import secrets
import random
from datetime import datetime, timedelta
from database import engine, SessionLocal
import models
from sqlalchemy.orm import Session

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
    password: str

class UserCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    phone: str
    password: str

class UserResponse(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: EmailStr
    phone: str


class Token(BaseModel):
    access_token: str
    token_type: str
    
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
        db.close
        
db_dependency = Annotated[Session, Depends(get_db)]

@app.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
async def login(user_data: UserLogin):
    # In a real application, you would:
    # 1. Retrieve the user from a database
    # 2. Verify the password using a secure hashing algorithm
    # 3. Generate a proper JWT token
    
    user = users_db.get(user_data.email)
    if not user or user_data.password != user.get("password"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Generate a token (use a proper JWT in production)
    token = secrets.token_hex(32)
    
    return {"access_token": token, "token_type": "bearer"}



@app.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(user_data: UserCreate):
    # Check if email already exists
    print("Checking if email exists:", user_data.email)
    if user_data.email in users_db:
        print("Email already registered")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Generate user ID
    user_id = secrets.token_hex(8)
    print("Generated user ID:", user_id)
    
    # Store user in mock database
    # In a real app, you would hash the password before storing
    print("Storing user data in database")
    users_db[user_data.email] = {
        "id": user_id,
        "first_name": user_data.first_name,
        "last_name": user_data.last_name,
        "email": user_data.email,
        "phone": user_data.phone,
        "password": user_data.password  # Should be hashed in production
    }
    
    # Return user data without password
    print("Returning user data")
    return {
        "id": user_id,
        "first_name": user_data.first_name,
        "last_name": user_data.last_name,
        "email": user_data.email,
        "phone": user_data.phone
    }


@app.post("/forgot-password", response_model=OTPResponse)
async def forgot_password(request: ForgotPasswordRequest):
    # Check if email exists
    if request.email not in users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )
    
    # Generate a 6-digit OTP
    otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    
    # Set expiration time (10 minutes)
    expiry = datetime.now() + timedelta(minutes=10)
    
    # Store OTP with expiration
    otp_store[request.email] = {
        "otp": otp,
        "expiry": expiry
    }
    
    # In a real app, send the OTP via email
    # For demo purposes, we'll return it directly
    return {
        "otp": otp,
        "expires_in": 600  # 10 minutes in seconds
    }

@app.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(request: ResetPasswordRequest):
    # Check if email exists
    if request.email not in users_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email not found"
        )
    
    # Check if OTP exists for this email
    if request.email not in otp_store:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No OTP requested for this email"
        )
    
    # Get stored OTP data
    otp_data = otp_store[request.email]
    
    # Check if OTP has expired
    if datetime.now() > otp_data["expiry"]:
        # Remove expired OTP
        del otp_store[request.email]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP has expired"
        )
    
    # Verify OTP
    if request.otp != otp_data["otp"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP"
        )
    
    # Update password
    users_db[request.email]["password"] = request.new_password
    
    # Remove used OTP
    del otp_store[request.email]
    
    return {"message": "Password reset successful"}

@app.get("/")
async def root():
    return {"message":"Hello!"}

