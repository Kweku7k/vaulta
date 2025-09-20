# auth_store.py
from datetime import timedelta
import os

import jwt
from redis_client import r

ACCESS_TTL = 60 * 15        # 15 minutes (adjust as needed)
OTP_TTL     = 60 * 10        # 10 minutes

def save_access_token(token: str, user_id: str) -> None:
    r.setex(f"access:{token}", ACCESS_TTL, user_id)

def get_user_id_from_token(token: str) -> str | None:
    return r.get(f"access:{token}")

def revoke_access_token(token: str) -> None:
    r.delete(f"access:{token}")

def save_user_otp(user_id: str, otp: str) -> None:
    r.setex(f"user_otp:{user_id}", OTP_TTL, otp)

def get_user_otp(user_id: str) -> str | None:
    return r.get(f"user_otp:{user_id}")

def clear_user_otp(user_id: str) -> None:
    r.delete(f"user_otp:{user_id}")
    
def get_user_by_id(user_id: str) -> None:
    from models import User
    from database import SessionLocal

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()
    return user

def get_user_by_jwt(token):
    from models import User
    from database import SessionLocal

    try:
        payload = jwt.decode(token, os.getenv("JWT_SECRET", "your_jwt_secret"), algorithms=["HS256"])
        user_id = payload.get("sub")
        if not user_id:
            return None
    except jwt.PyJWTError:
        return None

    db = SessionLocal()
    user = db.query(User).filter(User.id == user_id).first()
    db.close()
    return user
