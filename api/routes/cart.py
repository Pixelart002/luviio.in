import uuid
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from typing import Optional, List

# Aapki database aur security utilities
from api.db.database import get_db
from api.utils.security import verify_token

router = APIRouter(prefix="/api/cart", tags=["Cart"])

class CartItemAdd(BaseModel):
    product_id: str
    quantity: int = Field(default=1, gt=0)

# --- HELPER: Consistent User Identification ---
def get_user_id(request: Request):
    """
    User ki pehchan dhoondta hai: Pehle Access Token, fir Guest Cookie.
    Returns: (id_string, is_logged_in)
    """
    # 1. Check Login Token
    token = request.cookies.get("access_token")
    if token:
        payload = verify_token(token, "access")
        if payload and payload != "expired":
            # Login user ki ID Supabase me UUID string hoti hai
            return str(payload.get("sub")), True
    
    # 2. Check Guest ID from Cookie
    guest_id = request.cookies.get("guest_id")
    if guest_id:
        return guest_id, False
        
    return None, False

# ==========================================
# GET: FETCH CART
# ==========================================
@router.get("/")
async def get_cart(request: Request, response: Response):
    user_id, is_logged_in = get_user_id(request)
    db = get_db()
    
    # Agar user pehli baar aaya hai (bina login, bina guest_id)
    if not user_id:
        # Naya ID generate karo taaki session start ho jaye
        user_id = f"guest_{uuid.uuid4().hex}"
        # Cookie set karo: Lax use kar rahe hain taaki cross-request me block na ho
        response.set_cookie(
            key="guest_id", 
            value=user_id, 
            httponly=True, 
            secure=True, 
            samesite="lax", 
            max_age=2592000 # 30 days
        )
        return {"status": "success", "data": {"items": [], "subtotal": 0, "total_items": 0}}

    try:
        # DB Query: 'products' table ke saath join karke details laao
        # Note: Ensure karein ki 'cart_items' me 'product_id' foreign key hai
        cart_res = db.table("cart_items").select(
            "id, quantity, products(id, name, image_url, mrp)"
        ).eq("user_id", user_id).execute()

        items = cart_res.data or []
        subtotal = 0
        total_items = 0
        formatted_items = []

        for item in items:
            p = item.get("products")
            if not p:
                continue # Fail-safe: agar product DB se delete ho gaya ho
                
            qty = item.get("quantity", 0)
            price = p.get("mrp", 0)
            
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
        print(f"DEBUG CART FETCH ERROR: {e}")
        return {"status": "error", "message": "Failed to load cart"}

# ==========================================
# POST: ADD TO CART
# ==========================================
@router.post("/add")
async def add_to_cart(data: CartItemAdd, request: Request, response: Response):
    user_id, _ = get_user_id(request)
    db = get_db()
    
    # Agar Guest ID nahi hai, toh add karte waqt generate karo
    if not user_id:
        user_id = f"guest_{uuid.uuid4().hex}"
        response.set_cookie(
            key="guest_id", 
            value=user_id, 
            httponly=True, 
            secure=True, 
            samesite="lax", 
            max_age=2592000
        )

    try:
        # 1. Check karein ki item pehle se cart me hai ya nahi
        existing = db.table("cart_items").select("id, quantity").eq("user_id", user_id).eq("product_id", data.product_id).execute()
        
        if existing.data:
            # Sirf quantity badhao
            new_qty = existing.data[0]['quantity'] + data.quantity
            db.table("cart_items").update({"quantity": new_qty}).eq("id", existing.data[0]['id']).execute()
        else:
            # Naya item insert karo
            db.table("cart_items").insert({
                "user_id": user_id, 
                "product_id": data.product_id, 
                "quantity": data.quantity
            }).execute()

        return {"status": "success", "message": "Added to your collection"}
    except Exception as e:
        print(f"DEBUG CART ADD ERROR: {e}")
        raise HTTPException(status_code=500, detail="Database update failed")

# ==========================================
# DELETE: REMOVE ITEM
# ==========================================
@router.delete("/remove/{item_id}")
async def remove_cart_item(item_id: int, request: Request):
    user_id, _ = get_user_id(request)
    if not user_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        get_db().table("cart_items").delete().eq("id", item_id).eq("user_id", user_id).execute()
        return {"status": "success", "message": "Item removed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Delete failed")