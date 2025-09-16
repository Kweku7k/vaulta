from datetime import datetime, timedelta
import os

import jwt
from db.models import Customer
from models import User
from utils import generate_otp, send_email

def get_customer_by_email(email: str, db) -> Customer:
    """
    Retrieve a customer from the database by their email address
    
    Args:
        email (str): Email address to search for
        db: Database session object
        
    Returns:
        Customer: Customer object if found, None otherwise
    """
    print(f"Searching for customer with email: {email}")
    customer = db.query(User).filter(User.email == email).first()
    print("customer")
    print(customer)
    print(f"Customer found: {customer is not None}")
    return customer


def send_otp_to_email_for_login(user, db):
    print("Generating OTP for user login...")
    otp = generate_otp()
    print(f"Generated OTP: {otp}")
    
    print("Adding OTP to user record...")
    # add otp to user body
    # user.otp = otp
    
    print(f"Sending OTP email to {user.email}...")
    
    # send otp to user via email
    send_email("otp.html","OTP for Login", [user.email] ,context={"name":user.first_name, "otp":otp, "subject":f"OTP - {otp}"})

    print("Saving user record to database...")
    # save user to db
    db.commit()
    db.refresh(user)
    
    print("OTP email sent successfully")
    # This function should send an OTP to the user's email for login
    # For now, let's just return a mock response
    return {"status": "success", "message": "OTP sent to email"}

def issue_jwt_token(user_id):
    SECRET_KEY = os.getenv('JWT_SECRET')
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60

    # Create JWT token
    expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    jwt_payload = {
        "sub": user_id,
        "exp": expire
    }
    
    jwt_token = jwt.encode(jwt_payload, SECRET_KEY, algorithm=ALGORITHM)

    return {"message": "OTP verified", "user_id": user_id, "jwt_token": jwt_token}