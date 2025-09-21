from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime
from sqlalchemy.sql import func
from database import Base
    
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
    

class Customer(Base):
    __tablename__ = 'customer'
    
    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=True)
    signed_agreement_id = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    email = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    birth_date = Column(String, nullable=True)
    address = Column(String, nullable=True)
    tax_identification_number = Column(String, nullable=True)
    gov_id_image_front = Column(String, nullable=True)
    gov_id_image_back = Column(String, nullable=True)
    status = Column(String, nullable=True)

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customer.id"), nullable=False)
    amount = Column(Integer, nullable=False)
    currency = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    transaction_type = Column(String, nullable=False)  # e.g., 'deposit', 'withdrawal'
    provider = Column(String, nullable=False)  # e.g., 'deposit', 'withdrawal'
    status = Column(String, nullable=False)  # e.g., 'pending', 'completed', 'failed'
    reference = Column(String, unique=True, index=True, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())