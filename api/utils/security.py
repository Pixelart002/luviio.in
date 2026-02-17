import os
import logging
from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext

# Logger Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SECURITY-ENGINE")

# Configuration
SECRET_KEY = os.environ.get("SESSION_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 1           #
REFRESH_TOKEN_EXPIRE_DAYS = 30          #

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    logger.info("🔢 Step: Hashing password for secure storage")
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    logger.info("🔑 Step: Verifying password hash during login")
    return pwd_context.verify(plain_password, hashed_password)

def create_jwt_token(data: dict, expires_delta: timedelta, is_refresh: bool = False):
    """Generates a signed JWT using SESSION_SECRET."""
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    token_type = "refresh" if is_refresh else "access"
    
    to_encode.update({"exp": expire, "type": token_type})
    
    try:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"✅ Success: {token_type.capitalize()} token generated for {to_encode.get('sub')}")
        return encoded_jwt
    except Exception as e:
        logger.error(f"❌ Error: Token generation failed: {str(e)}")
        raise

def get_auth_tokens(user_id: str):
    logger.info(f"🚀 Initializing token issuance for User: {user_id}")
    access_token = create_jwt_token(
        data={"sub": user_id}, 
        expires_delta=timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    )
    refresh_token = create_jwt_token(
        data={"sub": user_id}, 
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        is_refresh=True
    )
    return access_token, refresh_token