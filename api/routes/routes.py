import os
from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

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
    # TODO: Save user to Database
    return RedirectResponse(url="/login", status_code=303)


# ==========================================
# 4. PARTNER NETWORK ROUTES (B2B)
# ==========================================
# A. Partner Landing Page (Shows Perks)
@router.get("/partner", response_class=HTMLResponse)
async def partner_landing_page(request: Request):
    return templates.TemplateResponse("app/pages/partner_landing.html", {"request": request})

# B. Partner Application Form (Shows Actual Form)
@router.get("/partner/apply", response_class=HTMLResponse)
async def partner_apply_page(request: Request):
    if request.cookies.get("luviio_auth"):
        return RedirectResponse(url="/dashboard", status_code=303)
        
    return templates.TemplateResponse("app/pages/partner.html", {"request": request})

# C. Partner Form Submit Logic
@router.post("/partner/apply")
async def process_partner(
    company_name: str = Form(...), 
    business_id: str = Form(...), 
    email: str = Form(...), 
    password: str = Form(...)
):
    # TODO: Save Partner Application to Database
    return RedirectResponse(url="/login", status_code=303)


# ==========================================
# 5. PROTECTED DASHBOARD
# ==========================================
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    auth_cookie = request.cookies.get("luviio_auth")
    
    # Prevent unauthorized access
    if not auth_cookie:
        return RedirectResponse(url="/login", status_code=303)
        
    # Temporary placeholder UI for Dashboard
    html_content = """
    <body style="background-color: #0a0a0a; color: white; height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; font-family: sans-serif;">
        <h1 style="margin-bottom: 20px;">Welcome to Luviio Dashboard</h1>
        <a href="/" style="color: #C5A059; text-decoration: none; padding: 10px 20px; border: 1px solid #C5A059; border-radius: 5px;">Go back Home</a>
    </body>
    """
    return HTMLResponse(content=html_content)