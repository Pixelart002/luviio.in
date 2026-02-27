from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from typing import Optional, List
import uuid

# Database aur Security functions import karein
from api.db.database import get_db, get_admin_db
from api.utils.security import verify_token

router = APIRouter(prefix="/api/cart", tags=["Cart"])

# 1. Validation Schema
class CartItemAdd(BaseModel):
    product_id: str
    quantity: int = Field(default=1, gt=0)

# --- Helper to get User Identity (Guest or Logged In) ---
def get_user_context(request: Request):
    # 1. Logged in check
    access_token = request.cookies.get("access_token")
    if access_token:
        payload = verify_token(access_token, "access")
        if payload and payload != "expired":
            return str(payload.get("sub")), "user"
    
    # 2. Guest check
    guest_id = request.cookies.get("guest_id")
    if guest_id:
        return guest_id, "guest"
    
    return None, None

# ==========================================
# GET: FETCH CART (FIXED)
# ==========================================
@router.get("/")
async def get_cart(request: Request, response: Response):
    user_id, user_type = get_user_context(request)
    db = get_db()
    
    # Agar user pehchan mein nahi aa raha, toh naya guest banado
    if not user_id:
        user_id = f"guest_{uuid.uuid4().hex}"
        response.set_cookie(key="guest_id", value=user_id, httponly=True, secure=True, max_age=2592000)
        return {"status": "success", "data": {"items": [], "subtotal": 0, "total_items": 0}}

    try:
        # Fetching items with join on products
        cart_res = db.table("cart_items").select(
            "id, quantity, products(id, name, image_url, mrp)"
        ).eq("user_id", user_id).execute()

        items = cart_res.data or []
        subtotal = 0
        total_items = 0
        formatted_items = []

        for item in items:
            p = item.get("products")
            if not p: continue
            
            qty = item.get("quantity", 0)
            price = p.get("mrp", 0) # MRP use kar rahe hain default
            
            subtotal += (price * qty)
            total_items += qty
            formatted_items.append({
                "cart_item_id": item["id"],
                "product_id": p["id"],
                "name": p["name"],
                "image_url": p["image_url"],
                "price": price,
                "quantity": qty
            })

        return {
            "status": "success",
            "data": {
                "items": formatted_items,
                "subtotal": subtotal,
                "total_items": total_items
            }
        }
    except Exception as e:
        print(f"DEBUG: Cart Fetch Error -> {e}")
        raise HTTPException(status_code=500, detail="Database connection error")

# ==========================================
# POST: ADD TO CART (FIXED)
# ==========================================
@router.post("/add")
async def add_to_cart(data: CartItemAdd, request: Request, response: Response):
    user_id, user_type = get_user_context(request)
    db = get_db()

    if not user_id:
        user_id = f"guest_{uuid.uuid4().hex}"
        response.set_cookie(key="guest_id", value=user_id, httponly=True, secure=True, max_age=2592000)

    try:
        # Existing item check
        existing = db.table("cart_items").select("*").eq("user_id", user_id).eq("product_id", data.product_id).execute()
        
        if existing.data:
            new_qty = existing.data[0]['quantity'] + data.quantity
            db.table("cart_items").update({"quantity": new_qty}).eq("id", existing.data[0]['id']).execute()
        else:
            db.table("cart_items").insert({
                "user_id": user_id,
                "product_id": data.product_id,
                "quantity": data.quantity
            }).execute()

        return {"status": "success", "message": "Added to cart"}
    except Exception as e:
        print(f"DEBUG: Cart Add Error -> {e}")
        raise HTTPException(status_code=500, detail="Failed to add item")