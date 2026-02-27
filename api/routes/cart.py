import uuid
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from api.db.database import get_db
from api.utils.security import verify_token

router = APIRouter(prefix="/api/cart", tags=["Cart"])

class CartItemAdd(BaseModel):
    product_id: str
    quantity: int = Field(default=1, gt=0)

def get_user_identity(request: Request):
    # 1. Check if logged in
    token = request.cookies.get("access_token")
    if token:
        payload = verify_token(token, "access")
        if payload and payload != "expired":
            return str(payload.get("sub")), "user"
    
    # 2. Check guest cookie
    guest_id = request.cookies.get("guest_id")
    if guest_id:
        return guest_id, "guest"
    
    return None, None

@router.get("/")
async def get_cart(request: Request, response: Response):
    user_id, _ = get_user_identity(request)
    db = get_db()
    
    if not user_id:
        # Naya guest banado agar kuch nahi mila
        user_id = f"guest_{uuid.uuid4().hex}"
        response.set_cookie(key="guest_id", value=user_id, httponly=True, secure=True, max_age=2592000)
        return {"status": "success", "data": {"items": [], "subtotal": 0}}

    try:
        # Supabase Join query to get product details
        res = db.table("cart_items").select("id, quantity, products(id, name, image_url, mrp)").eq("user_id", user_id).execute()
        items = res.data or []
        
        subtotal = 0
        formatted = []
        for item in items:
            p = item.get("products")
            if not p: continue
            price = p.get("mrp", 0)
            subtotal += (price * item["quantity"])
            formatted.append({
                "id": item["id"],
                "name": p["name"],
                "image": p["image_url"],
                "price": price,
                "qty": item["quantity"]
            })
            
        return {"status": "success", "data": {"items": formatted, "subtotal": subtotal}}
    except Exception as e:
        print(f"Error: {e}")
        return {"status": "error", "message": "Failed to load cart"}

@router.post("/add")
async def add_to_cart(data: CartItemAdd, request: Request, response: Response):
    user_id, _ = get_user_identity(request)
    db = get_db()
    
    if not user_id:
        user_id = f"guest_{uuid.uuid4().hex}"
        response.set_cookie(key="guest_id", value=user_id, httponly=True, secure=True, max_age=2592000)

    # Logic: Check if exists -> Update or Insert
    existing = db.table("cart_items").select("*").eq("user_id", user_id).eq("product_id", data.product_id).execute()
    
    if existing.data:
        new_qty = existing.data[0]['quantity'] + data.quantity
        db.table("cart_items").update({"quantity": new_qty}).eq("id", existing.data[0]['id']).execute()
    else:
        db.table("cart_items").insert({"user_id": user_id, "product_id": data.product_id, "quantity": data.quantity}).execute()
        
    return {"status": "success", "message": "Added to your collection"}

@router.delete("/remove/{item_id}")
async def remove_item(item_id: int, request: Request):
    user_id, _ = get_user_identity(request)
    if not user_id: raise HTTPException(status_code=401)
    get_db().table("cart_items").delete().eq("id", item_id).eq("user_id", user_id).execute()
    return {"status": "success"}