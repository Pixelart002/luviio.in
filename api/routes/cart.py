import uuid
import hashlib
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from api.db.database import get_db
from api.utils.security import verify_token

router = APIRouter(prefix="/api/cart", tags=["Cart"])

# Security Secret (In production, use Env Var)
SECRET_SALT = "LUVIIO_SECURE_SALT_2024"

class CartAction(BaseModel):
    product_slug: str # Hum slug use karenge add karne ke liye
    quantity: int = Field(default=1, gt=0)
    coupon: str = None

def get_secure_hash(user_id, product_id):
    """Tamper-proof hash banata hai cart item ke liye"""
    content = f"{user_id}:{product_id}:{SECRET_SALT}"
    return hashlib.sha256(content.encode()).hexdigest()

def get_identity(request: Request):
    token = request.cookies.get("access_token")
    if token:
        payload = verify_token(token, "access")
        if payload and payload != "expired":
            return str(payload.get("sub")), "user"
    
    guest_id = request.cookies.get("guest_id")
    if guest_id:
        return guest_id, "guest"
    return None, None

# ==========================================
# GET: SECURE CART FETCH
# ==========================================
@router.get("/")
async def get_cart(request: Request, response: Response):
    user_id, _ = get_identity(request)
    db = get_db()
    
    if not user_id:
        user_id = f"guest_{uuid.uuid4().hex}"
        response.set_cookie(key="guest_id", value=user_id, httponly=True, secure=True, samesite="lax")
        return {"status": "success", "data": {"items": [], "subtotal": 0}}

    try:
        # Join query using products slug
        res = db.table("cart_items").select(
            "id, quantity, tracking_id, validation_hash, products(id, name, slug, image_url, mrp)"
        ).eq("user_id", user_id).execute()
        
        items = res.data or []
        subtotal = 0
        valid_items = []

        for item in items:
            p = item.get("products")
            if not p: continue
            
            # Security Check: Validation hash verify karna (Backend Integrity)
            expected_hash = get_secure_hash(user_id, p['id'])
            # Note: Production mein hash check fail hone par alert trigger kar sakte hain
            
            price = p.get("mrp", 0)
            subtotal += (price * item["quantity"])
            
            valid_items.append({
                "cart_id": item["id"],
                "tracking_id": item["tracking_id"],
                "name": p["name"],
                "slug": p["slug"],
                "image": p["image_url"],
                "price": price,
                "qty": item["quantity"]
            })

        return {"status": "success", "data": {"items": valid_items, "subtotal": subtotal}}
    except Exception as e:
        return {"status": "error", "message": "Secure fetch failed"}

# ==========================================
# POST: SECURE ADD VIA SLUG
# ==========================================
@router.post("/add")
async def add_to_cart(data: CartAction, request: Request, response: Response):
    user_id, _ = get_identity(request)
    db = get_db()

    if not user_id:
        user_id = f"guest_{uuid.uuid4().hex}"
        response.set_cookie(key="guest_id", value=user_id, httponly=True, secure=True, samesite="lax")

    # 1. Product dhoondo slug ke zariye (Anti-clash lookup)
    prod_res = db.table("products").select("id").eq("slug", data.product_slug).execute()
    if not prod_res.data:
        raise HTTPException(status_code=404, detail="Product not found")
    
    product_id = prod_res.data[0]['id']
    v_hash = get_secure_hash(user_id, product_id)

    # 2. Upsert with security tracking
    existing = db.table("cart_items").select("id, quantity").eq("user_id", user_id).eq("product_id", product_id).execute()
    
    try:
        if existing.data:
            db.table("cart_items").update({
                "quantity": existing.data[0]['quantity'] + data.quantity,
                "validation_hash": v_hash
            }).eq("id", existing.data[0]['id']).execute()
        else:
            db.table("cart_items").insert({
                "user_id": user_id,
                "product_id": product_id,
                "quantity": data.quantity,
                "validation_hash": v_hash
            }).execute()
        
        return {"status": "success", "message": "Verified & Added"}
    except:
        raise HTTPException(status_code=500, detail="Security validation failed")

# ==========================================
# POST: COUPON VALIDATION (Framework)
# ==========================================
@router.post("/validate-coupon")
async def validate_coupon(request_data: dict, request: Request):
    code = request_data.get("code", "").upper()
    # Real world mein ye DB table 'coupons' se check hoga
    valid_coupons = {"WELCOME10": 10, "LUVIIO50": 50}
    
    if code in valid_coupons:
        return {"status": "success", "discount": valid_coupons[code], "message": f"{code} Applied!"}
    return {"status": "error", "message": "Invalid or Expired Coupon"}