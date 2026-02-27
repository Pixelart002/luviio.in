from pydantic import BaseModel, EmailStr, Field
from typing import Optional

# ==========================================
# USER SCHEMAS (B2C)
# ==========================================
class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, description="Full name of the user")
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")

# ==========================================
# PARTNER SCHEMAS (B2B)
# ==========================================
class PartnerCreate(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=100)
    business_id: str = Field(..., min_length=3, description="GSTIN or Business Reg Number")
    email: EmailStr
    password: str = Field(..., min_length=8)

# ==========================================
# LOGIN SCHEMA
# ==========================================
class UserLogin(BaseModel):
    email: EmailStr
    password: str