from pydantic import BaseModel, EmailStr
from typing import List, Optional
from datetime import datetime

# Choice schemas
class ChoiceBase(BaseModel):
    choice_text: str
    is_correct: bool

class ChoiceCreate(ChoiceBase):
    pass

class Choice(ChoiceBase):
    id: int
    question_id: int
    
    class Config:
        orm_mode = True

# Question schemas
class QuestionBase(BaseModel):
    question_text: str

class QuestionCreate(QuestionBase):
    choices: List[ChoiceCreate]

class Question(QuestionBase):
    id: int
    choices: List[Choice] = []
    
    class Config:
        orm_mode = True

# User authentication schemas
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    first_name: str
    last_name: str
    phone: str
    password: str

class UserLogin(UserBase):
    password: str

class UserResponse(UserBase):
    id: str
    first_name: str
    last_name: str
    phone: str
    
    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

# Password reset schemas
class ForgotPasswordRequest(UserBase):
    pass

class OTPResponse(BaseModel):
    otp: str
    expires_in: int

class ResetPasswordRequest(UserBase):
    otp: str
    new_password: str