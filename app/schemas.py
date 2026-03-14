from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from app.models import OrderStatus, UserRole


# ── Auth ──────────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    user_id: Optional[str] = None
    role: Optional[str] = None

class RefreshRequest(BaseModel):
    refresh_token: str


# ── User ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=255)

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, min_length=8, max_length=128)

class UserRead(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}

class UserAdminUpdate(BaseModel):
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None


# ── Address ───────────────────────────────────────────────────────────────────

class AddressCreate(BaseModel):
    line1: str = Field(max_length=255)
    line2: Optional[str] = Field(default=None, max_length=255)
    city: str = Field(max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    postal_code: str = Field(max_length=20)
    country: str = Field(min_length=2, max_length=2)
    is_default: bool = False

class AddressRead(AddressCreate):
    id: str
    user_id: str
    model_config = {"from_attributes": True}


# ── Category ──────────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(max_length=100)
    slug: str = Field(max_length=120, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None

class CategoryRead(CategoryCreate):
    id: str
    created_at: datetime
    model_config = {"from_attributes": True}


# ── Product ───────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str = Field(max_length=255)
    slug: str = Field(max_length=280, pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    price: Decimal = Field(gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    sku: Optional[str] = Field(default=None, max_length=100)
    stock: int = Field(ge=0, default=0)
    is_active: bool = True
    image_url: Optional[str] = Field(default=None, max_length=500)
    category_id: Optional[str] = None
    weight_grams: Optional[int] = Field(default=None, ge=0)

class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    price: Optional[Decimal] = Field(default=None, gt=0, decimal_places=2)
    compare_price: Optional[Decimal] = None
    sku: Optional[str] = Field(default=None, max_length=100)
    stock: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    image_url: Optional[str] = None
    category_id: Optional[str] = None
    weight_grams: Optional[int] = None

class ProductRead(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    price: Decimal
    compare_price: Optional[Decimal]
    sku: Optional[str]
    stock: int
    is_active: bool
    image_url: Optional[str]
    category: Optional[CategoryRead]
    weight_grams: Optional[int]
    created_at: datetime
    model_config = {"from_attributes": True}

class ProductListRead(BaseModel):
    id: str
    name: str
    slug: str
    price: Decimal
    compare_price: Optional[Decimal]
    stock: int
    is_active: bool
    image_url: Optional[str]
    category_id: Optional[str]
    model_config = {"from_attributes": True}


# ── Order ─────────────────────────────────────────────────────────────────────

class OrderItemCreate(BaseModel):
    product_id: str
    quantity: int = Field(ge=1, le=100)

class OrderItemRead(BaseModel):
    id: str
    product_id: Optional[str]
    product_name: str
    unit_price: Decimal
    quantity: int
    subtotal: Decimal
    model_config = {"from_attributes": True}

class OrderCreate(BaseModel):
    items: List[OrderItemCreate] = Field(min_length=1)
    shipping_address_id: str
    notes: Optional[str] = Field(default=None, max_length=500)

class OrderRead(BaseModel):
    id: str
    status: OrderStatus
    subtotal: Decimal
    shipping_cost: Decimal
    tax: Decimal
    total: Decimal
    currency: str
    stripe_payment_intent: Optional[str]
    shipping_address: Optional[str]
    tracking_number: Optional[str]
    notes: Optional[str]
    items: List[OrderItemRead]
    created_at: datetime
    model_config = {"from_attributes": True}

class OrderAdminUpdate(BaseModel):
    status: Optional[OrderStatus] = None
    tracking_number: Optional[str] = Field(default=None, max_length=100)


# ── Payment ───────────────────────────────────────────────────────────────────

class PaymentIntentCreate(BaseModel):
    order_id: str

class PaymentIntentRead(BaseModel):
    client_secret: str
    payment_intent_id: str


# ── Generic ───────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
    pages: int

class MessageResponse(BaseModel):
    message: str
