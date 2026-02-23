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
    # 1. Admin DB client lene ki koshish karo
    admin_db = get_admin_db()
    
    # 2. DEBUG CHECK: Agar admin_db initialize nahi hua (Keys missing hain)
    if admin_db is None:
        return HTMLResponse(content=f"""
            <div style="background: #111; color: #ff4d4d; padding: 30px; font-family: sans-serif; border: 2px solid red; border-radius: 10px; margin: 50px;">
                <h1 style="color: #fff; border-bottom: 1px solid #333; pb: 10px;">❌ System Configuration Error</h1>
                <p style="font-size: 18px;">Bhai, <b>SB_SERVICE_ROLE_KEY</b> backend ko nahi mil rahi hai.</p>
                <ul style="color: #ccc;">
                    <li>Agar Local hai: <b>.env</b> file check karo.</li>
                    <li>Agar Vercel hai: Dashboard ke <b>Environment Variables</b> check karo.</li>
                </ul>
            </div>
        """, status_code=500)

    # 3. Password hashing
    hashed_pwd = hash_password(password)
    
    try:
        # 4. Supabase insertion attempt
        # Dhyan rahe table ka naam 'users' hi hona chahiye Supabase mein
        response = admin_db.table("users").insert({
            "name": name,
            "email": email,
            "password_hash": hashed_pwd,
            "tier": "standard",
            "tags": ["b2c_website", "new_user"]
        }).execute()
        
        # Success Redirect
        return RedirectResponse(url="/login?msg=account_created", status_code=303)
        
    except Exception as e:
        # 5. ASLI ERROR DEBUGGER: Agar Supabase ne mana kiya (e.g. Email already exists)
        error_str = str(e)
        print(f"DEBUG: Supabase Insertion Error -> {error_str}")
        
        return HTMLResponse(content=f"""
            <div style="background: #000; color: #ffcc00; padding: 30px; font-family: monospace; border: 1px solid #333; border-radius: 8px; margin: 50px;">
                <h1 style="color: red;">🚨 Supabase Error Detected</h1>
                <p style="font-size: 16px; background: #222; padding: 15px; border-radius: 5px;">{error_str}</p>
                <div style="margin-top: 20px; color: #888;">
                    <p><b>Checklist:</b></p>
                    <ul>
                        <li>Kya Supabase mein <b>'users'</b> naam ki table hai?</li>
                        <li>Kya <b>email</b> unique constraint ki wajah se error aa raha hai?</li>
                        <li>Kya <b>password_hash</b> column ka naam sahi hai?</li>
                    </ul>
                </div>
                <a href="/register" style="display: inline-block; margin-top: 20px; color: #fff; background: #C5A059; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Back to Signup</a>
            </div>
        """, status_code=400)
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
        
