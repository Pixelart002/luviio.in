import os
import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext

# Bcrypt algorithm setup (truncate_error=False add karna zaroori hai)
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__truncate_error=False # Ye passlib ko error fekne se rokega
)

JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-luviio-key-12345")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

def hash_password(password: str) -> str:
    """Plain password ko secure hash me convert karega (Max 72 chars fix ke sath)"""
    # Safety Check: Password ko 72 characters par cut (truncate) kar do
    safe_password = password[:72]
    return pwd_context.hash(safe_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Login ke waqt password check karne ke liye."""
    # Verification ke time bhi same 72 char logic lagana hoga
    safe_password = plain_password[:72]
    return pwd_context.verify(safe_password, hashed_password)

def create_access_token(data: dict) -> str:
    """User/Partner details ka ek secure token banayega."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt