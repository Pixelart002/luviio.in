import uuid
from fastapi import APIRouter, Request, Response, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from api.db.database import get_db
from api.utils.security import verify_token

router = APIRouter(prefix="/api/cart", tags=["Cart"])

# ==========================================
# 1. PYDANTIC SCHEMAS
# ==========================================
class CartItemAdd(BaseModel):
    product_id: str
    quantity: int = Field(default=1, gt=0, description="Quantity must be at least 1")

class CartItemUpdate(BaseModel):
    cart_item_id: int
    quantity: int = Field(default=1, gt=0)

# ==========================================
# 2. HELPER: GUEST OR USER IDENTIFIER
# ==========================================
def get_cart_identifier(request: Request):
    """
    Check karta hai ki user logged in hai ya guest hai.
    Returns: (cart_owner_id, user_type, new_guest_id_to_set_in_cookie)
    """
    # 1. Check logged in user
    access_token = request.cookies.get("access_token")
    if access_token:
        payload = verify_token(access_token, "access")
        if payload and payload != "expired":
            return payload.get("sub"), "user", None
            
    # 2. Check existing guest
    guest_id = request.cookies.get("guest_id")
    if guest_id:
        return guest_id, "guest", None
        
    # 3. Create new guest
    new_guest_id = f"guest_{uuid.uuid4().hex}"
    return new_guest_id, "guest", new_guest_id

# ==========================================
# POST: ADD TO CART
# ==========================================
@router.post("/add")
async def add_to_cart(request_data: CartItemAdd, request: Request, response: Response):
    db = get_db()
    owner_id, owner_type, new_guest_id = get_cart_identifier(request)
    
    # Agar naya guest hai, toh usko cookie chipkao
    if new_guest_id:
        response.set_cookie(key="guest_id", value=new_guest_id, httponly=True, secure=True, max_age=2592000) # 30 days
        
    try:
        # Check existing item
        existing_item = db.table("cart_items").select("*").eq("user_id", owner_id).eq("product_id", request_data.product_id).execute()
        
        if existing_item.data:
            # Update quantity
            new_qty = existing_item.data[0]['quantity'] + request_data.quantity
            db.table("cart_items").update({"quantity": new_qty}).eq("id", existing_item.data[0]['id']).execute()
        else:
            # Insert new
            db.table("cart_items").insert({
                "user_id": owner_id,
                "product_id": request_data.product_id,
                "quantity": request_data.quantity
            }).execute()

        return {"status": "success", "message": "Added to your collection"}
        
    except Exception as e:
        print(f"Cart Add Error: {e}")
        raise HTTPException(status_code=500, detail="Could not add item to cart")

# ==========================================
# GET: FETCH CART 
# ==========================================
@router.get("/")
async def get_cart(request: Request, response: Response):
    db = get_db()
    owner_id, owner_type, new_guest_id = get_cart_identifier(request)
    
    if new_guest_id:
        response.set_cookie(key="guest_id", value=new_guest_id, httponly=True, secure=True, max_age=2592000)
        return {"status": "success", "data": {"items": [], "subtotal": 0, "total_items": 0}}

    try:
        cart_response = db.table("cart_items").select(
            "id, quantity, products(id, name, image_url, display_price, original_mrp, material_finish)"
        ).eq("user_id", owner_id).execute()

        items = cart_response.data
        
        sponsored_item = {
            "product_id": "SPON-001",
            "name": "Onyx Liquid Dispenser",
            "image_url": "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=200",
            "price": 2499,
            "material_finish": "Matte Black"
        }

        if not items:
            return {"status": "success", "message": "Cart is empty", "data": {"items": [], "subtotal": 0, "total_items": 0, "sponsored": sponsored_item}}

        subtotal = 0
        total_items = 0
        formatted_items = []

        for item in items:
            product = item.get("products")
            if not product: continue
                
            qty = item.get("quantity")
            price = product.get("display_price", 0)
            
            subtotal += (price * qty)
            total_items += qty
            
            formatted_items.append({
                "cart_item_id": item.get("id"),
                "product_id": product.get("id"),
                "name": product.get("name"),
                "image_url": product.get("image_url"),
                "price": price,
                "original_mrp": product.get("original_mrp"),
                "material_finish": product.get("material_finish"),
                "quantity": qty
            })

        return {"status": "success", "data": {"items": formatted_items, "subtotal": subtotal, "total_items": total_items, "sponsored": sponsored_item}}

    except Exception as e:
        print(f"Cart Fetch Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cart")

# ==========================================
# PUT: UPDATE QUANTITY
# ==========================================
@router.put("/update")
async def update_cart_item(request_data: CartItemUpdate, request: Request):
    db = get_db()
    owner_id, _, _ = get_cart_identifier(request)
    
    try:
        db.table("cart_items").update({"quantity": request_data.quantity}).eq("id", request_data.cart_item_id).eq("user_id", owner_id).execute()
        return {"status": "success", "message": "Cart updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not update cart")

# ==========================================
# DELETE: REMOVE ITEM
# ==========================================
@router.delete("/remove/{item_id}")
async def remove_cart_item(item_id: int, request: Request):
    db = get_db()
    owner_id, _, _ = get_cart_identifier(request)
    
    try:
        db.table("cart_items").delete().eq("id", item_id).eq("user_id", owner_id).execute()
        return {"status": "success", "message": "Item removed"}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not remove item")

# ==========================================
# POST: CHECKOUT VALIDATION (The Masterstroke)
# ==========================================
@router.post("/checkout/validate")
async def validate_checkout(request: Request):
    owner_id, owner_type, _ = get_cart_identifier(request)
    
    # AGAR BANDA GUEST HAI, TOH BOLO PEHLE SIGN IN KARE!
    if owner_type == "guest":
        return {
            "status": "auth_required", 
            "redirect_url": "/login?checkout=true",
            "message": "Please sign in or create an account to securely checkout."
        }
        
    return {"status": "success", "redirect_url": "/checkout"}