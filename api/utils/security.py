import os
import jwt
import bcrypt
from datetime import datetime, timedelta

# JWT Settings
JWT_SECRET = os.getenv("JWT_SECRET", "luviio_premium_bathware_secure_jwt_secret_key_2026_xyz_abcdef123456")
JWT_ALGORITHM = "HS256"

# 2-Token System Timings
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Chhota time (Safe)
REFRESH_TOKEN_EXPIRE_DAYS = 7     # Lamba time (User ko bar bar login nahi karna padega)

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')[:72] 
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_byte_enc = plain_password.encode('utf-8')[:72]
    hashed_password_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(password_byte_enc, hashed_password_bytes)

def create_tokens(data: dict):
    """Access Token aur Refresh Token dono ek saath banata hai."""
    
    # 1. Access Token (Short-lived)
    access_payload = data.copy()
    access_expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_payload.update({"exp": access_expire, "token_type": "access"})
    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    # 2. Refresh Token (Long-lived, isme bhi basic details dalenge taaki refresh karte waqt data mil jaye)
    refresh_payload = data.copy()
    refresh_expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_payload.update({"exp": refresh_expire, "token_type": "refresh"})
    refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    return access_token, refresh_token

def verify_token(token: str, expected_type: str = "access"):
    """Token ki validity aur uska type check karta hai."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # Check if token type matches (taaki koi refresh token daal ke access na le le)
        if payload.get("token_type") != expected_type:
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return "expired"  # Backend ko pata chalega ki naya token dena hai
    except jwt.InvalidTokenError:
        return None       # Fake/Tampered token