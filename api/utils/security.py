from passlib.context import CryptContext

# Bcrypt algorithm set kar rahe hain
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Plain password ko secure hash me convert karega."""
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Login ke waqt password check karne ke liye."""
    return pwd_context.verify(plain_password, hashed_password)