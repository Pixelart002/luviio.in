import os
from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from api.db.database import get_db, get_admin_db
# Dhyan do: ab hum 'create_tokens' import kar rahe hain
from api.utils.security import hash_password, verify_password, create_tokens, verify_token

from slowapi import Limiter
from slowapi.util import get_remote_address

router = APIRouter()
db = get_db()
limiter = Limiter(key_func=get_remote_address)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


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
    
    # Agar naya access token bana hai backend me, toh use cookie me set kar do
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
    if request.cookies.get("refresh_token"): # Refresh token hai matlab banda logged in hai
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
    
    # --- 2-TOKEN SYSTEM START ---
    access_token, refresh_token = create_tokens(token_payload)
    
    response = RedirectResponse(url="/dashboard", status_code=303)
    
    # Set Access Token Cookie (30 mins = 1800 seconds)
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
    
    # Set Refresh Token Cookie (7 Days = 604800 seconds)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=True, samesite="strict", max_age=604800)
    
    return response

@router.get("/logout")
async def logout_user():
    response = RedirectResponse(url="/", status_code=303)
    # Dono cookies delete kardo
    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    return response


# ==========================================
# 3. REGISTRATION ROUTES (Same as before)
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
# 4. PARTNER ROUTES (Same as before)
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
# 5. SECURE DASHBOARD (Protected with Refresh Logic)
# ==========================================
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    payload, new_access_token = manage_session(request)
    
    # Agar donu token kachra nikle, toh kick out karo
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
    
    # Agar 30 minute poore ho gaye the aur backend ne chup-chaap naya token banaya hai, toh use browser me update kardo
    if new_access_token:
        response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
        
    return response






# ==========================================
# 7. CONTENT PAGES (Collection, Gallery, Story)
# ==========================================

@router.get("/collection", response_class=HTMLResponse)
async def collection_page(request: Request):
    payload, new_access_token = manage_session(request)
    
    current_user = None
    discount_percentage = 0
    
    # 1. User/Partner Check
    if payload and payload != "expired":
        current_user = {
            "name": payload.get("name"), 
            "email": payload.get("email"), 
            "tier": payload.get("tier"),
            "type": payload.get("type")
        }
        # RULE ENGINE: Agar partner hai, toh 35% wholesale discount do
        if current_user["type"] == "partner":
            discount_percentage = 35 

    # 2. Database se active products laao
    admin_db = get_admin_db()
    try:
        product_response = admin_db.table("products").select("*").eq("is_active", True).execute()
        products = product_response.data
    except Exception as e:
        print(f"DB Error: {e}")
        products = []

    # 3. Dynamic Price Calculation
    for product in products:
        mrp = product["mrp"]
        if discount_percentage > 0:
            # Partner Price
            discounted_price = mrp - (mrp * (discount_percentage / 100))
            product["display_price"] = int(discounted_price)
            product["original_mrp"] = int(mrp)
        else:
            # Normal B2C Price
            product["display_price"] = int(mrp)
            product["original_mrp"] = None

    # 4. Render Template
    response = templates.TemplateResponse(
        "app/pages/collection.html", 
        {
            "request": request, 
            "user": current_user,
            "products": products
        }
    )
    
    # Session refresh logic
    if new_access_token:
        response.set_cookie(key="access_token", value=new_access_token, httponly=True, secure=True, samesite="strict", max_age=1800)
        
    return response