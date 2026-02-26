from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Optional, List

# Yahan tumhara supabase client import hoga jahan bhi tumne usko initialize kiya hai
# Example: from api.database import supabase 

router = APIRouter(prefix="/api/cart", tags=["Cart"])

# 1. Validation Schema (Strict Backend Validation)
class CartItemAdd(BaseModel):
    product_id: str
    quantity: int = Field(default=1, gt=0, description="Quantity must be at least 1")

# ==========================================
# POST: ADD TO CART
# ==========================================
@router.post("/add")
async def add_to_cart(request_data: CartItemAdd, request: Request):
    # 1. Authentication Check (Fail Fast)
    # Using getattr to safely check if user exists in state
    user = getattr(request.state, "user", None)
    
    if not user:
        raise HTTPException(status_code=401, detail="Session expired. Please login.")

    user_id = user.get("id")
    
    try:
        # 2. Check if product already exists in cart
        existing_item = supabase.table("cart_items").select("*").eq("user_id", user_id).eq("product_id", request_data.product_id).execute()
        
        if existing_item.data:
            # Agar pehle se hai, toh sirf quantity badhao
            new_qty = existing_item.data[0]['quantity'] + request_data.quantity
            supabase.table("cart_items").update({"quantity": new_qty}).eq("id", existing_item.data[0]['id']).execute()
        else:
            # Naya item hai toh insert karo
            supabase.table("cart_items").insert({
                "user_id": user_id,
                "product_id": request_data.product_id,
                "quantity": request_data.quantity
            }).execute()

        return {"status": "success", "message": "Added to your collection"}
        
    except Exception as e:
        print(f"Cart Add Error: {e}")
        raise HTTPException(status_code=500, detail="Could not add item to cart")

# ==========================================
# GET: FETCH CART (With Sponsored Item)
# ==========================================
@router.get("/")
async def get_cart(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    user_id = user.get("id")

    try:
        # Fetch Cart Items with Product Details
        cart_response = supabase.table("cart_items").select(
            "id, quantity, products(id, name, image_url, display_price, original_mrp, material_finish)"
        ).eq("user_id", user_id).execute()

        items = cart_response.data

        # 🔥 SPONSORED PRODUCT LOGIC
        # Real-world mein yeh DB se aayega, abhi hum isko statically pass kar rahe hain
        sponsored_item = {
            "product_id": "SPON-001",
            "name": "Onyx Liquid Dispenser",
            "image_url": "https://images.unsplash.com/photo-1620626011761-996317b8d101?auto=format&fit=crop&w=200",
            "price": 2499,
            "material_finish": "Matte Black"
        }

        # 3. NULL IS A STATE (Empty Cart Handle Karo)
        if not items:
            return {
                "status": "success",
                "message": "Cart is empty",
                "data": {
                    "items": [],
                    "subtotal": 0,
                    "total_items": 0,
                    "sponsored": sponsored_item  # Empty cart me bhi upsell karenge!
                }
            }

        # Calculate Subtotal & Formatting
        subtotal = 0
        total_items = 0
        formatted_items = []

        for item in items:
            product = item.get("products")
            if not product:
                continue # Fail-safe
                
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

        return {
            "status": "success",
            "data": {
                "items": formatted_items,
                "subtotal": subtotal,
                "total_items": total_items,
                "sponsored": sponsored_item # Filled cart me bhi upsell
            }
        }

    except Exception as e:
        print(f"Cart Fetch Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch cart")