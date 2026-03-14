import json
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_active_user, require_admin
from app.models import Address, Order, OrderItem, OrderStatus, Product, User
from app.schemas import OrderAdminUpdate, OrderCreate, OrderRead, PaginatedResponse

router = APIRouter(prefix="/orders", tags=["Orders"])

SHIPPING_THRESHOLD = Decimal("75.00")   # free shipping above this
SHIPPING_FLAT      = Decimal("9.99")
TAX_RATE           = Decimal("0.08")    # 8 %


def _build_order(payload: OrderCreate, user: User, db: Session) -> Order:
    # Validate address ownership
    address = db.query(Address).filter(
        Address.id == payload.shipping_address_id,
        Address.user_id == user.id,
    ).first()
    if not address:
        raise HTTPException(status_code=404, detail="Shipping address not found")

    subtotal = Decimal("0")
    order_items = []

    for item_in in payload.items:
        product: Product = db.query(Product).filter(
            Product.id == item_in.product_id,
            Product.is_active == True,
        ).with_for_update().first()          # row-level lock to prevent overselling

        if not product:
            raise HTTPException(status_code=404, detail=f"Product {item_in.product_id} not found")
        if product.stock < item_in.quantity:
            raise HTTPException(
                status_code=409,
                detail=f"Insufficient stock for '{product.name}' (available: {product.stock})",
            )

        # Deduct stock
        product.stock -= item_in.quantity
        line_total = product.price * item_in.quantity
        subtotal += line_total

        order_items.append(
            OrderItem(
                product_id=product.id,
                product_name=product.name,
                unit_price=product.price,
                quantity=item_in.quantity,
                subtotal=line_total,
            )
        )

    shipping = Decimal("0") if subtotal >= SHIPPING_THRESHOLD else SHIPPING_FLAT
    tax = (subtotal + shipping) * TAX_RATE
    total = subtotal + shipping + tax

    order = Order(
        user_id=user.id,
        subtotal=subtotal,
        shipping_cost=shipping,
        tax=tax.quantize(Decimal("0.01")),
        total=total.quantize(Decimal("0.01")),
        shipping_address=json.dumps({
            "line1": address.line1,
            "line2": address.line2,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postal_code,
            "country": address.country,
        }),
        notes=payload.notes,
    )
    order.items = order_items
    return order


# ── Customer endpoints ────────────────────────────────────────────────────────

@router.post("/", response_model=OrderRead, status_code=201)
def create_order(
    payload: OrderCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    order = _build_order(payload, current_user, db)
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("/my", response_model=List[OrderRead])
def my_orders(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Order)
        .filter(Order.user_id == current_user.id)
        .order_by(Order.created_at.desc())
        .offset(skip).limit(limit)
        .all()
    )


@router.get("/my/{order_id}", response_model=OrderRead)
def get_my_order(
    order_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == current_user.id,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.post("/my/{order_id}/cancel", response_model=OrderRead)
def cancel_order(
    order_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == order_id, Order.user_id == current_user.id
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order.status not in (OrderStatus.pending,):
        raise HTTPException(status_code=409, detail=f"Cannot cancel order in '{order.status}' status")

    # Restore stock
    for item in order.items:
        if item.product_id:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product:
                product.stock += item.quantity

    order.status = OrderStatus.cancelled
    db.commit()
    db.refresh(order)
    return order


# ── Admin endpoints ───────────────────────────────────────────────────────────

@router.get("/", response_model=PaginatedResponse, dependencies=[Depends(require_admin)])
def list_all_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: OrderStatus = None,
    db: Session = Depends(get_db),
):
    q = db.query(Order)
    if status_filter:
        q = q.filter(Order.status == status_filter)
    q = q.order_by(Order.created_at.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        items=[OrderRead.model_validate(o) for o in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size),
    )


@router.patch("/{order_id}", response_model=OrderRead, dependencies=[Depends(require_admin)])
def admin_update_order(
    order_id: str,
    payload: OrderAdminUpdate,
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if payload.status:
        order.status = payload.status
    if payload.tracking_number is not None:
        order.tracking_number = payload.tracking_number
    db.commit()
    db.refresh(order)
    return order
