# auth_store.py
from datetime import timedelta
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