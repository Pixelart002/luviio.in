import os
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from api.db.database import get_db, get_admin_db
from api.utils.security import hash_password, verify_password, create_tokens, verify_token
# Global template engine import
from api.core.template_engine import templates 

router = APIRouter()
db = get_db()

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

    response = templates.TemplateResponse("pages/index.html", {
        "request": request, 
        "user": current_user
    })
    
    if new_access_token:
        response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
        
    return response

@router.get("/home")
async def redirect_to_index():
    return RedirectResponse(url="/", status_code=301)


# ==========================================
# 2. LOGIN & LOGOUT (WITH CART MERGE 🔥)
# ==========================================
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.cookies.get("refresh_token"): 
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("pages/login.html", {"request": request})

@router.post("/login")
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
    
    # 🔥 GROWTH HACK: MERGE GUEST CART TO LOGGED IN USER
    guest_id = request.cookies.get("guest_id")
    if guest_id:
        try:
            admin_db.table("cart_items").update({"user_id": str(account["id"])}).eq("user_id", guest_id).execute()
            response.delete_cookie(key="guest_id") # Clean up guest cookie
        except Exception as e:
            print(f"Cart Merge Error: {e}")
            
    return response

@router.get("/logout")
async def logout_user():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    return response

# ==========================================
# 3. REGISTRATION ROUTES (WITH CART MERGE 🔥)
# ==========================================
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if request.cookies.get("refresh_token"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("pages/register.html", {"request": request})

@router.post("/register")
async def process_register(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    admin_db = get_admin_db()
    hashed_pwd = hash_password(password)
    try:
        # Insert user and get the returned row
        res = admin_db.table("users").insert({"name": name, "email": email, "password_hash": hashed_pwd, "tier": "standard", "tags": ["b2c_website"]}).execute()
        
        response = RedirectResponse(url="/login?msg=account_created", status_code=303)
        
        # 🔥 MERGE CART ON REGISTRATION
        if res.data:
            new_user_id = str(res.data[0]["id"])
            guest_id = request.cookies.get("guest_id")
            if guest_id:
                admin_db.table("cart_items").update({"user_id": new_user_id}).eq("user_id", guest_id).execute()
                response.delete_cookie(key="guest_id")
                
        return response
    except Exception as e:
        print(e)
        return RedirectResponse(url="/register?error=email_exists", status_code=303)


# ==========================================
# 4. PARTNER ROUTES
# ==========================================
@router.get("/partner", response_class=HTMLResponse)
async def partner_landing_page(request: Request):
    return templates.TemplateResponse("pages/partner_landing.html", {"request": request})

@router.get("/partner/apply", response_class=HTMLResponse)
async def partner_apply_page(request: Request):
    if request.cookies.get("refresh_token"):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("pages/partner.html", {"request": request})

@router.post("/partner/apply")
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
    
    response = templates.TemplateResponse("pages/dashboard.html", {"request": request, "user": current_user})
    
    if new_access_token:
        response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
        
    return response


# ==========================================
# 6. CONTENT PAGES (Collection, Gallery)
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
        "pages/collection.html", 
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
        "pages/product.html", 
        {
            "request": request, 
            "user": current_user,
            "product": product
        }
    )
    
    if new_access_token:
        page_response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
        
    return page_response