import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext

# ==========================================
# 1. SETUP
# ==========================================
# Bcrypt algorithm use kar rahe hain password hashing ke liye
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration (Vercel env variables se aayega)
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fallback-secret-key-for-local-dev-only")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# ==========================================
# 2. PASSWORD HASHING
# ==========================================
def hash_password(password: str) -> str:
    """Plain password ko bcrypt hash me convert karega"""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check karega ki login password aur DB ka hash match hota hai ya nahi"""
    return pwd_context.verify(plain_password, hashed_password)

# ==========================================
# 3. JWT TOKEN MANAGEMENT
# ==========================================
def create_tokens(data: dict):
    """User ke login hone par Access aur Refresh token banayega"""
    # 1. Access Token (Short lived - 30 mins)
    access_payload = data.copy()
    access_expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_payload.update({"exp": access_expire, "token_type": "access"})
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)

    # 2. Refresh Token (Long lived - 7 Days)
    # Refresh token me kam data rakhte hain security ke liye
    refresh_payload = {
        "sub": data.get("sub"), 
        "email": data.get("email"), 
        "type": data.get("type")
    }
    refresh_expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_payload.update({"exp": refresh_expire, "token_type": "refresh"})
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)

    return access_token, refresh_token

def verify_token(token: str, expected_type: str = "access"):
    """Token ki validity aur expiry check karega"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("token_type") != expected_type:
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return "expired"  # Specific keyword bhej rahe hain taaki routes ko pata chale
    except JWTError:
        return None