from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_active_user, require_admin
from app.models import User
from app.schemas import UserRead, UserUpdate, UserAdminUpdate, AddressCreate, AddressRead
from app.security import hash_password

router = APIRouter(prefix="/users", tags=["Users"])


# ── Profile ───────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserRead)
def get_me(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.patch("/me", response_model=UserRead)
def update_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    if payload.full_name is not None:
        current_user.full_name = payload.full_name
    if payload.password is not None:
        current_user.hashed_password = hash_password(payload.password)
    db.commit()
    db.refresh(current_user)
    return current_user


# ── Addresses ─────────────────────────────────────────────────────────────────

@router.get("/me/addresses", response_model=List[AddressRead])
def list_addresses(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return current_user.addresses


@router.post("/me/addresses", response_model=AddressRead, status_code=201)
def add_address(
    payload: AddressCreate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    from app.models import Address
    if payload.is_default:
        for addr in current_user.addresses:
            addr.is_default = False
    addr = Address(**payload.model_dump(), user_id=current_user.id)
    db.add(addr)
    db.commit()
    db.refresh(addr)
    return addr


@router.delete("/me/addresses/{address_id}", status_code=204)
def delete_address(
    address_id: str,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    from app.models import Address
    addr = db.query(Address).filter(
        Address.id == address_id, Address.user_id == current_user.id
    ).first()
    if not addr:
        raise HTTPException(status_code=404, detail="Address not found")
    db.delete(addr)
    db.commit()


# ── Admin ─────────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[UserRead], dependencies=[Depends(require_admin)])
def list_users(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(User).offset(skip).limit(limit).all()


@router.patch("/{user_id}", response_model=UserRead, dependencies=[Depends(require_admin)])
def admin_update_user(
    user_id: str,
    payload: UserAdminUpdate,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role is not None:
        user.role = payload.role
    db.commit()
    db.refresh(user)
    return user
