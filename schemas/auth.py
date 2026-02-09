from pydantic import BaseModel, EmailStr, Field

class AuthSchema(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

class SignupSchema(AuthSchema):
    # Add extra fields for signup if needed
    pass