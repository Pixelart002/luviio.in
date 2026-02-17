import os
from datetime import datetime, timedelta, timezone
from typing import Tuple
from jose import jwt
from passlib.context import CryptContext

SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-key")
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain, hashed) -> bool:
    return pwd_context.verify(plain, hashed)

def get_auth_tokens(user_id: str) -> Tuple[str, str]:
    # ... (Iska code pichle msg se copy kar lena)
    # Short version for verification:
    access = jwt.encode({"sub": user_id, "type": "access", "exp": datetime.now(timezone.utc) + timedelta(minutes=60)}, SECRET_KEY, algorithm=ALGORITHM)
    refresh = jwt.encode({"sub": user_id, "type": "refresh", "exp": datetime.now(timezone.utc) + timedelta(days=30)}, SECRET_KEY, algorithm=ALGORITHM)
    return access, refresh