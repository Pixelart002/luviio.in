# backend/core/security.py
import os
from datetime import datetime, timedelta
from typing import Optional, Any, Union
import jwt
from passlib.context import CryptContext

# 1. Password Hashing Setup (Bcrypt algorithm use kar rahe hain)
# Yeh plain password (jaise 'password123') ko ek ajeeb string mein convert kar dega
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 2. JWT Settings
# Real world mein SECRET_KEY ko .env file mein rakhte hain.
# Agar .env mein nahi mili, toh fallback ek random string hogi (sirf dev ke liye)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "luviio_super_secret_key_2026_change_in_production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 7 Days expiry

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check karta hai ki user ka dala hua password hash se match karta hai ya nahi"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Naya password save karne se pehle usko encrypt karta hai"""
    return pwd_context.hash(password)

def create_access_token(
    subject: Union[str, Any], expires_delta: Optional[timedelta] = None
) -> str:
    """Login ke baad user ke liye ek JWT token banata hai"""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    # Payload: Wo data jo token ke andar chupa hota hai (e.g., user_id)
    to_encode = {"exp": expire, "sub": str(subject)}
    
    # Token generate karna
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt