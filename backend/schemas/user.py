# backend/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional

# 1. Base Schema (Jo fields har jagah common hain)
class UserBase(BaseModel):
    email: EmailStr # Yeh automatically check karega ki email '@' aur '.com' ke sath valid hai ya nahi

# 2. Signup Schema (Frontend se Signup karte waqt kya data aayega)
class UserCreate(UserBase):
    name: str = Field(..., min_length=2, max_length=50, description="Name 2 se 50 characters ke beech hona chahiye")
    password: str = Field(..., min_length=6, description="Password kam se kam 6 characters ka hona chahiye")

# 3. Login Schema (Frontend se Login karte waqt kya aayega)
class UserLogin(UserBase):
    password: str

# 4. Response Schema (Jab User create hoga, toh hum kya wapas bhejenge)
# 🚨 DHYAN DEIN: Isme 'password' field nahi hai! Hum kabhi password wapas nahi bhejte.
class UserResponse(UserBase):
    id: str
    name: str
    created_at: datetime
    is_active: bool = True

# 5. Token Schema (JWT Token ka format)
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: Optional[str] = None