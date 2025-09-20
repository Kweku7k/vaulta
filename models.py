from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.sql import func
from database import Base

class Questions(Base):
    __tablename__ = "questions"
    
    id = Column(Integer, primary_key=True, index=True)
    question_text = Column(String, index=True)
    
class Choices(Base):
    __tablename__ = 'choices'
    
    id = Column(Integer, primary_key=True, index=True)
    choice_text = Column(String, index=True)
    is_correct = Column(Boolean, default=False)
    question_id = Column(Integer, ForeignKey("questions.id"))
    
class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    password = Column(String)
    # usermetadata = Column(String, nullable=True)
    # user_meta_data = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class OTP(Base):
    __tablename__ = "otps"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True)
    otp = Column(String)
    expiry = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    class ApiKey(Base):
        __tablename__ = "api_keys"

        id = Column(Integer, primary_key=True, index=True)
        key = Column(String, unique=True, index=True, nullable=False)
        user_id = Column(String, ForeignKey("users.id"), nullable=False)
        created_at = Column(DateTime(timezone=True), server_default=func.now())
        expires_at = Column(DateTime(timezone=True), nullable=True)
        is_active = Column(Boolean, default=True)