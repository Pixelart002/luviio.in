import sys
import os

# ==========================================
# 🔥 1. VERCEL PATH FIX (SABSE UPAR)
# ==========================================
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from api.db.database import get_db, get_admin_db
from api.utils.security import hash_password, verify_password, create_tokens, verify_token

from slowapi import Limiter
from slowapi.util import get_remote_address

from config.ui_config import UI_CONFIG

router = APIRouter()
db = get_db()
limiter = Limiter(key_func=get_remote_address)

# ==========================================
# 🔥 2. TEMPLATES & GLOBAL CONFIG SETUP
# ==========================================
TEMPLATE_DIR = os.path.join(ROOT_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# MAGIC TRICK: Is ek line se ui_config har page (login, dashboard, home) me automatically chala jayega!
templates.env.globals['ui_config'] = UI_CONFIG


# --- HELPER FUNCTION FOR SESSION MANAGEMENT ---
def manage_session(request: Request):
    """Ye check karega ki token zinda hai ya naya banana padega."""
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")
    
    payload = None
    new_access_token = None

    if access_token:
        payload = verify_token(access_token, "access")
        
    # Agar access token nahi hai YA expire ho gaya hai
    if not access_token or payload == "expired":
        if refresh_token:
            refresh_payload = verify_token(refresh_token, "refresh")
            # Agar refresh token theek hai, toh session renew karo
            if refresh_payload and refresh_payload != "expired":
                token_data = {
                    "sub": refresh_payload.get("sub"),
                    "email": refresh_payload.get("email"),
                    "type": refresh_payload.get("type"),
                    "name": refresh_payload.get("name"),
                    "tier": refresh_payload.get("tier")
                }
                new_access_token, _ = create_tokens(token_data)
                payload = verify_token(new_access_token, "access")
            else:
                payload = None # Refresh token bhi bekar ho gaya
        else:
            payload = None

    return payload, new_access_token


# ==========================================
# 1. MAIN HOMEPAGE
# ==========================================
@router.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    payload, new_access_token = manage_session(request)
    current_user = None 
    
    if payload and payload != "expired":
        current_user = {
            "name": payload.get("name"), 
            "email": payload.get("email"), 
            "tier": payload.get("tier"),
            "type": payload.get("type")
        }

    response = templates.TemplateResponse("app/pages/index.html", {"request": request, "user": current_user})
    
    if new_access_token:
        response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
        
    return response

@router.get("/home")
async def redirect_to_index():
    return RedirectResponse(url="/", status_code=301)


# ==========================================
# 2. LOGIN & LOGOUT
# ==========================================
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.cookies.get("refresh_token"): 
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("app/pages/login.html", {"request": request})

@router.post("/login")
@limiter.limit("5/minute")
async def process_login(request: Request, email: str = Form(...), password: str = Form(...)):
    admin_db = get_admin_db()
    account = None
    account_type = "user"
    
    user_response = admin_db.table("users").select("*").eq("email", email).execute()
    if len(user_response.data) > 0:
        account = user_response.data[0]
    else:
        partner_response = admin_db.table("partners").select("*").eq("email", email).execute()
        if len(partner_response.data) > 0:
            account = partner_response.data[0]
            account_type = "partner"
            
    if not account:
        return RedirectResponse(url="/login?error=user_not_found", status_code=303)
        
    if not verify_password(password, account["password_hash"]):
        return RedirectResponse(url="/login?error=invalid_password", status_code=303)
        
    token_payload = {
        "sub": str(account["id"]), 
        "email": account["email"],
        "type": account_type, 
        "name": account.get("name") or account.get("company_name"),
        "tier": account.get("tier")
    }
    
    access_token, refresh_token = create_tokens(token_payload)
    
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True, samesite="strict", max_age=604800)
    
    return response

@router.get("/logout")
async def logout_user():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    return response


# ==========================================
# 3. REGISTRATION ROUTES
# ==========================================
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if request.cookies.get("refresh_token"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("app/pages/register.html", {"request": request})

@router.post("/register")
@limiter.limit("5/minute")
async def process_register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    admin_db = get_admin_db()
    hashed_pwd = hash_password(password)
    try:
        admin_db.table("users").insert({"name": name, "email": email, "password_hash": hashed_pwd, "tier": "standard", "tags": ["b2c_website"]}).execute()
        return RedirectResponse(url="/login?msg=account_created", status_code=303)
    except:
        return RedirectResponse(url="/register?error=email_exists", status_code=303)


# ==========================================
# 4. PARTNER ROUTES
# ==========================================
@router.get("/partner", response_class=HTMLResponse)
async def partner_landing_page(request: Request):
    return templates.TemplateResponse("app/pages/partner_landing.html", {"request": request})

@router.get("/partner/apply", response_class=HTMLResponse)
async def partner_apply_page(request: Request):
    if request.cookies.get("refresh_token"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("app/pages/partner.html", {"request": request})

@router.post("/partner/apply")
@limiter.limit("5/minute")
async def process_partner(request: Request, company_name: str = Form(...), business_id: str = Form(...), email: str = Form(...), password: str = Form(...)):
    admin_db = get_admin_db()
    hashed_pwd = hash_password(password)
    try:
        admin_db.table("partners").insert({"company_name": company_name, "business_id": business_id, "email": email, "password_hash": hashed_pwd, "status": "pending", "tier": "trade_partner", "tags": ["b2b_lead"]}).execute()
        return RedirectResponse(url="/login?msg=partner_application_received", status_code=303)
    except:
        return RedirectResponse(url="/partner/apply?error=application_failed", status_code=303)


# ==========================================
# 5. SECURE DASHBOARD
# ==========================================
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    payload, new_access_token = manage_session(request)
    
    if not payload or payload == "expired":
        response = RedirectResponse(url="/login?error=invalid_session", status_code=303)
        response.delete_cookie(key="access_token")
        response.delete_cookie(key="refresh_token")
        return response
        
    current_user = {
        "name": payload.get("name", "User"),
        "email": payload.get("email", ""),
        "tier": payload.get("tier", "standard"),
        "type": payload.get("type", "user")
    }
    
    response = templates.TemplateResponse("app/pages/dashboard.html", {"request": request, "user": current_user})
    
    if new_access_token:
        response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
        
    return response


# ==========================================
# 6. CONTENT PAGES (Collection, Gallery, Story)
# ==========================================
@router.get("/collection", response_class=HTMLResponse)
async def collection_page(request: Request):
    payload, new_access_token = manage_session(request)
    
    current_user = None
    discount_percentage = 0
    
    if payload and payload != "expired":
        current_user = {
            "name": payload.get("name"), 
            "email": payload.get("email"), 
            "tier": payload.get("tier"),
            "type": payload.get("type")
        }
        if current_user["type"] == "partner":
            discount_percentage = 35 

    admin_db = get_admin_db()
    try:
        product_response = admin_db.table("products").select("*").eq("is_active", True).execute()
        products = product_response.data
    except Exception as e:
        print(f"DB Error: {e}")
        products = []

    for product in products:
        mrp = product["mrp"]
        if discount_percentage > 0:
            discounted_price = mrp - (mrp * (discount_percentage / 100))
            product["display_price"] = int(discounted_price)
            product["original_mrp"] = int(mrp)
        else:
            product["display_price"] = int(mrp)
            product["original_mrp"] = None

    response = templates.TemplateResponse(
        "app/pages/collection.html", 
        {
            "request": request, 
            "user": current_user,
            "products": products
        }
    )
    
    if new_access_token:
        response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
        
    return response
    
    
@router.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail_page(request: Request, product_id: str):
    payload, new_access_token = manage_session(request)
    current_user = None
    discount_percentage = 0
    
    if payload and payload != "expired":
        current_user = {
            "name": payload.get("name"), 
            "email": payload.get("email"), 
            "tier": payload.get("tier"),
            "type": payload.get("type")
        }
        if current_user["type"] == "partner":
            discount_percentage = 35 

    admin_db = get_admin_db()
    try:
        response = admin_db.table("products").select("*").eq("id", product_id).eq("is_active", True).execute()
        if not response.data:
            return RedirectResponse(url="/collection?error=product_not_found", status_code=303)
        product = response.data[0]
    except Exception as e:
        print(f"DB Error: {e}")
        return RedirectResponse(url="/collection?error=product_not_found", status_code=303)

    mrp = product["mrp"]
    if discount_percentage > 0:
        product["display_price"] = int(mrp - (mrp * (discount_percentage / 100)))
        product["original_mrp"] = int(mrp)
    else:
        product["display_price"] = int(mrp)
        product["original_mrp"] = None

    page_response = templates.TemplateResponse(
        "app/pages/product.html", 
        {
            "request": request, 
            "user": current_user,
            "product": product
        }
    )
    
    if new_access_token:
        page_response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
        
    return page_response


# ==========================================
# 7. CART API (AJAX endpoints)
# ==========================================
@router.post("/api/cart/add")
async def add_to_cart(request: Request):
    payload, _ = manage_session(request)
    
    if not payload or payload == "expired":
        return JSONResponse({"status": "error", "message": "Please log in to add items."}, status_code=401)
        
    user_id = payload.get("sub") 
    
    try:
        data = await request.json()
        product_id = data.get("product_id")
        quantity = int(data.get("quantity", 1))
    except:
        return JSONResponse({"status": "error", "message": "Invalid request data."}, status_code=400)

    admin_db = get_admin_db()
    
    try:
        existing_item = admin_db.table("cart_items").select("*").eq("user_id", user_id).eq("product_id", product_id).execute()
        
        if len(existing_item.data) > 0:
            new_qty = existing_item.data[0]["quantity"] + quantity
            admin_db.table("cart_items").update({"quantity": new_qty}).eq("id", existing_item.data[0]["id"]).execute()
        else:
            admin_db.table("cart_items").insert({
                "user_id": user_id,
                "product_id": product_id,
                "quantity": quantity
            }).execute()
            
        return JSONResponse({"status": "success", "message": "Item added to cart!"})
        
    except Exception as e:
        print(f"Cart Error: {e}")
        return JSONResponse({"status": "error", "message": "Could not add item to cart."}, status_code=500)