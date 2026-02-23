import os
from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from api.utils.security import hash_password
from api.db.database import get_db, get_admin_db

router = APIRouter()

db = get_db()

# --- TEMPLATE CONFIGURATION ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)


# ==========================================
# 1. MAIN HOMEPAGE ROUTE
# ==========================================
@router.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    
    # Browser se 'luviio_auth' naam ki cookie read karo
    auth_cookie = request.cookies.get("luviio_auth")
    current_user = None 
    
    # Dummy verification
    if auth_cookie == "valid_token_123":
        current_user = {
            "name": "Trade Partner", 
            "email": "partner@luviio.in", 
            "business_id": "LUV-PREMIUM-01"
        }

    return templates.TemplateResponse(
        "app/pages/index.html", 
        {
            "request": request,
            "user": current_user  
        }
    )

@router.get("/home")
async def redirect_to_index():
    return RedirectResponse(url="/", status_code=301)


# ==========================================
# 2. LOGIN & LOGOUT ROUTES
# ==========================================
@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if request.cookies.get("luviio_auth"):
        return RedirectResponse(url="/dashboard", status_code=303)
        
    return templates.TemplateResponse("app/pages/login.html", {"request": request})

@router.post("/login")
async def process_login(email: str = Form(...), password: str = Form(...)):
    # TODO: Verify credentials from Database
    
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="luviio_auth", 
        value="valid_token_123", 
        httponly=True, 
        secure=True, 
        max_age=86400 
    )
    return response

@router.get("/logout")
async def logout_user():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="luviio_auth")
    return response


# ==========================================
# 3. USER REGISTRATION (B2C)
# ==========================================
@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if request.cookies.get("luviio_auth"):
        return RedirectResponse(url="/dashboard", status_code=303)
        
    return templates.TemplateResponse("app/pages/register.html", {"request": request})

@router.post("/register")
async def process_register(name: str = Form(...), email: str = Form(...), password: str = Form(...)):
    admin_db = get_admin_db()
    
    # 1. Check karo ki Admin DB load hua ya nahi
    if not admin_db:
        return HTMLResponse("<h1>Error:</h1><p>Admin DB client initialize nahi hua. Apni .env file me SB_SERVICE_ROLE_KEY check karo.</p>")
        
    hashed_pwd = hash_password(password)
    
    try:
        response = admin_db.table("users").insert({
            "name": name,
            "email": email,
            "password_hash": hashed_pwd,
            "tier": "standard",
            "tags": ["b2c_website", "new_user"]
        }).execute()
        
        return RedirectResponse(url="/login?msg=account_created", status_code=303)
        
    except Exception as e:
        # ASLI ERROR YAHAN SCREEN PAR DIKHEGA
        print(f"REAL SUPABASE ERROR: {str(e)}")
        return HTMLResponse(f"<div style='background: black; color: red; padding: 20px; font-family: sans-serif;'><h1>Asli Error Pata Chal Gaya:</h1><p>{str(e)}</p></div>")
# ==========================================
# 4. PARTNER NETWORK ROUTES (B2B)
# ==========================================
@router.get("/partner", response_class=HTMLResponse)
async def partner_landing_page(request: Request):
    return templates.TemplateResponse("app/pages/partner_landing.html", {"request": request})

@router.get("/partner/apply", response_class=HTMLResponse)
async def partner_apply_page(request: Request):
    if request.cookies.get("luviio_auth"):
        return RedirectResponse(url="/dashboard", status_code=303)
        
    return templates.TemplateResponse("app/pages/partner.html", {"request": request})

@router.post("/partner/apply")
async def process_partner(
    company_name: str = Form(...), 
    business_id: str = Form(...), 
    email: str = Form(...), 
    password: str = Form(...)
):
    admin_db = get_admin_db()
    hashed_pwd = hash_password(password)
    
    try:
        response = admin_db.table("partners").insert({
            "company_name": company_name,
            "business_id": business_id,
            "email": email,
            "password_hash": hashed_pwd,
            "status": "pending",           # Partner default pending rahega admin review tak
            "tier": "trade_partner",       # Default tier
            "tags": ["b2b_lead", "website_form"]
        }).execute()
        
        return RedirectResponse(url="/login?msg=partner_application_received", status_code=303)
        
    except Exception as e:
        print(f"Partner Creation Error: {str(e)}")
        return RedirectResponse(url="/partner/apply?error=application_failed", status_code=303)
# ==========================================
# 5. PROTECTED DASHBOARD
# ==========================================
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    auth_cookie = request.cookies.get("luviio_auth")
    
    if not auth_cookie:
        return RedirectResponse(url="/login", status_code=303)
        
    html_content = """
    <body style="background-color: #0a0a0a; color: white; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; font-family: sans-serif;">
        <h1 style="margin-bottom: 20px;">Welcome to Luviio Dashboard</h1>
        <a href="/" style="color: #C5A059; text-decoration: none; padding: 10px 20px; border: 1px solid #C5A059; border-radius: 5px;">Go back Home</a>
    </body>
    """
    return HTMLResponse(content=html_content)
    
    
# ==========================================
# 6. DATABASE CONNECTION TEST ROUTE
# ==========================================
@router.get("/test-db")
async def test_db_connection():
    try:
        # get_db() local variable hata diya kyunki wo already global declared hai
        admin_db = get_admin_db()
        
        status = {
            "message": "Supabase Connection Successful! 🎉",
            "url_loaded": bool(os.getenv("SB_URL")),
            "anon_key_loaded": bool(db),
            "service_role_loaded": bool(admin_db)
        }
        return status
    except Exception as e:
        return {"error": f"Connection fail ho gaya bhai: {str(e)}"}
        
