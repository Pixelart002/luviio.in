import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, func,
)
from sqlalchemy.orm import relationship
from app.database import Base
import enum


def utcnow():
    return datetime.now(timezone.utc)


# ── Enums ─────────────────────────────────────────────────────────────────────

class UserRole(str, enum.Enum):
    admin = "admin"
    customer = "customer"

class OrderStatus(str, enum.Enum):
    pending   = "pending"
    paid      = "paid"
    shipped   = "shipped"
    delivered = "delivered"
    cancelled = "cancelled"
    refunded  = "refunded"


# ── Models ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email         = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name     = Column(String(255))
    role          = Column(Enum(UserRole), default=UserRole.customer, nullable=False)
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    updated_at    = Column(DateTime(timezone=True), onupdate=func.now())

    orders        = relationship("Order", back_populates="user", lazy="dynamic")
    addresses     = relationship("Address", back_populates="user", cascade="all, delete-orphan")


class Address(Base):
    __tablename__ = "addresses"

    id         = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id    = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    line1      = Column(String(255), nullable=False)
    line2      = Column(String(255))
    city       = Column(String(100), nullable=False)
    state      = Column(String(100))
    postal_code = Column(String(20), nullable=False)
    country    = Column(String(2), nullable=False)   # ISO-3166 alpha-2
    is_default = Column(Boolean, default=False)

    user       = relationship("User", back_populates="addresses")


class Category(Base):
    __tablename__ = "categories"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(100), unique=True, nullable=False)
    slug        = Column(String(120), unique=True, nullable=False, index=True)
    description = Column(Text)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    products    = relationship("Product", back_populates="category", lazy="dynamic")


class Product(Base):
    __tablename__ = "products"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(255), nullable=False)
    slug        = Column(String(280), unique=True, nullable=False, index=True)
    description = Column(Text)
    price       = Column(Numeric(10, 2), nullable=False)
    compare_price = Column(Numeric(10, 2))          # original / crossed-out price
    sku         = Column(String(100), unique=True, index=True)
    stock       = Column(Integer, default=0, nullable=False)
    is_active   = Column(Boolean, default=True, nullable=False)
    image_url   = Column(String(500))
    category_id = Column(String(36), ForeignKey("categories.id", ondelete="SET NULL"))
    weight_grams = Column(Integer)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    updated_at  = Column(DateTime(timezone=True), onupdate=func.now())

    category    = relationship("Category", back_populates="products")
    order_items = relationship("OrderItem", back_populates="product")


class Order(Base):
    __tablename__ = "orders"

    id                  = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id             = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status              = Column(Enum(OrderStatus), default=OrderStatus.pending, nullable=False, index=True)
    subtotal            = Column(Numeric(10, 2), nullable=False)
    shipping_cost       = Column(Numeric(10, 2), default=0)
    tax                 = Column(Numeric(10, 2), default=0)
    total               = Column(Numeric(10, 2), nullable=False)
    currency            = Column(String(3), default="USD", nullable=False)
    stripe_payment_intent = Column(String(255), unique=True, index=True)
    shipping_address    = Column(Text)              # JSON snapshot
    tracking_number     = Column(String(100))
    notes               = Column(Text)
    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), onupdate=func.now())

    user   = relationship("User", back_populates="orders")
    items  = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id    = Column(String(36), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id  = Column(String(36), ForeignKey("products.id", ondelete="SET NULL"))
    product_name = Column(String(255), nullable=False)  # snapshot
    unit_price  = Column(Numeric(10, 2), nullable=False)  # snapshot
    quantity    = Column(Integer, nullable=False)
    subtotal    = Column(Numeric(10, 2), nullable=False)

    order   = relationship("Order", back_populates="items")
    product = relationship("Product", back_populates="order_items")
