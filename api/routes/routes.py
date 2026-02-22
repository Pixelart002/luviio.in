import os
from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# 1. Main Index Route (Reading the Cookie)
@router.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    
    # Browser se 'luviio_auth' naam ki cookie read karo
    auth_cookie = request.cookies.get("luviio_auth")
    
    current_user = None 
    
    # Agar cookie exist karti hai aur valid hai (abhi dummy check lagaya hai)
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

# 2. Handle Login Form Submit (Setting the Cookie)
# Note: Form(...) use kiya hai taaki HTML form data catch kar sakein
@router.post("/login")
async def process_login(email: str = Form(...), password: str = Form(...)):
    
    # TODO: Yahan Database se email/password check karna
    # Agar details sahi hain:
    
    # Login success hone ke baad wapas Homepage ("/") par bhejenge
    response = RedirectResponse(url="/", status_code=303)
    
    # --- COOKIE SET KARNE KA LOGIC ---
    # httponly=True (JavaScript isko chura nahi sakta - XSS attack se safe)
    # secure=True (Sirf HTTPS/SSL par kaam karegi, Vercel by default HTTPS deta hai)
    # max_age=86400 (Cookie 24 ghante baad expire ho jayegi)
    response.set_cookie(
        key="luviio_auth", 
        value="valid_token_123", # Future me yahan actual JWT token dalega
        httponly=True, 
        secure=True, 
        max_age=86400 
    )
    
    return response

# 3. Logout Logic (Deleting the Cookie)
@router.get("/logout")
async def logout_user():
    
    # Logout hote hi wapas homepage par bhej do
    response = RedirectResponse(url="/", status_code=303)
    
    # --- COOKIE DELETE KARNE KA LOGIC ---
    response.delete_cookie(key="luviio_auth")
    
    return response

# ==========================================
# --- OTHER PLACEHOLDER ROUTES ---
# ==========================================

@router.get("/home")
async def redirect_to_index():
    return RedirectResponse(url="/", status_code=301)

@router.get("/login")
async def login_page(request: Request):
    return {"message": "B2C Login Page chalegi yahan."}

@router.get("/register")
async def register_page(request: Request):
    return {"message": "B2C Sign Up Page chalegi yahan."}

@router.get("/partner")
async def partner_page(request: Request):
    return {"message": "B2B Partner Portal & Signup chalega yahan."}

@router.get("/dashboard")
async def dashboard_page(request: Request):
    auth_cookie = request.cookies.get("luviio_auth")
    if not auth_cookie:
        return RedirectResponse(url="/login", status_code=303)
        
    return {"message": "User/Partner Dashboard chalega yahan."}