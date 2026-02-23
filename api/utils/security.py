import os
import jwt
import bcrypt
from datetime import datetime, timedelta

# JWT Settings
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-luviio-key-12345")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

def hash_password(password: str) -> str:
    """Password ko hash karta hai aur 72-byte ki bcrypt limit ko handle karta hai."""
    # Bcrypt strictly needs bytes, aur 72 bytes se bada password allow nahi karta
    pwd_bytes = password.encode('utf-8')[:72] 
    
    # Salt generate karke hash banao
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    
    # Wapas string me convert karke return karo taaki DB me text ki tarah save ho
    return hashed_password.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check karta hai ki plain password aur hashed password match karte hain ya nahi."""
    # Dono ko bytes me convert karo, plain_password ko truncate karna zaroori hai
    password_byte_enc = plain_password.encode('utf-8')[:72]
    hashed_password_bytes = hashed_password.encode('utf-8')
    
    # Bcrypt ka native function use karo verify karne ke liye
    return bcrypt.checkpw(password_byte_enc, hashed_password_bytes)

def create_access_token(data: dict) -> str:
    """User/Partner details ka ek secure JWT token banayega."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

# --- NAYA FUNCTION ADD KIYA HAI ---
def verify_token(token: str):
    """Token ki security aur validity check karne ke liye."""
    try:
        # Secret key aur algorithm se signature verify hoga
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        print("Token expire ho chuka hai.")
        return None 
    except jwt.InvalidTokenError:
        print("Fake ya tampered token pakda gaya!")
        return None