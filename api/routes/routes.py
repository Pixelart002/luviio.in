import os
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) 
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# 1. Main Index Route
@router.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    
    # --- AUTHENTICATION LOGIC ---
    # TODO: Yahan apna actual authentication logic lagao (e.g. JWT token check ya Session check)
    
    # Logged Out State Test karne ke liye:
    current_user = None 
    
    # Logged In State Test karne ke liye isko uncomment kar do:
    # current_user = {
    #     "name": "Vikram Singhania", 
    #     "email": "vikram@luviio.in", 
    #     "business_id": "LUV-PREMIUM-01"
    # }

    return templates.TemplateResponse(
        "app/pages/index.html", 
        {
            "request": request,
            "user": current_user  
        }
    )

# 2. Redirect Route (/home se / par bhejne ke liye)
@router.get("/home")
async def redirect_to_index():
    # Status code 301 means "Permanent Redirect"
    return RedirectResponse(url="/", status_code=301)


# ==========================================
# --- NAYE PLACEHOLDER ROUTES (FRONTEND LINKS KE LIYE) ---
# ==========================================

# 3. User Login Page
@router.get("/login")
async def login_page(request: Request):
    # TODO: Return login.html template here later
    return {"message": "B2C Login Page chalegi yahan."}

# 4. Handle Login Form Submit (Drawer wale form se jo request aayegi)
@router.post("/login")
async def process_login(request: Request):
    # TODO: Verify email/password and create session
    return {"message": "Login form data received. Verifying..."}

# 5. User Sign Up Page
@router.get("/register")
async def register_page(request: Request):
    # TODO: Return register.html template here later
    return {"message": "B2C Sign Up Page chalegi yahan."}

# 6. Partner/Dealer Portal (B2B ke liye alag page)
@router.get("/partner")
async def partner_page(request: Request):
    # TODO: Return partner.html template here later
    return {"message": "B2B Partner Portal & Signup chalega yahan."}

# 7. Dashboard (Logged in users ke liye)
@router.get("/dashboard")
async def dashboard_page(request: Request):
    # TODO: Check if user is logged in, then show dashboard.html
    return {"message": "User/Partner Dashboard chalega yahan."}

# 8. Logout Logic
@router.get("/logout")
async def logout_user():
    # TODO: Clear session/cookie here
    # Logout hone ke baad wapas homepage par bhej do
    return RedirectResponse(url="/", status_code=303)