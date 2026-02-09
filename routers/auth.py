from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from schemas.auth import AuthSchema

router = APIRouter(prefix="/auth")
templates = Jinja2Templates(directory="templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})

@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse("auth/signup.html", {"request": request})

@router.post("/login")
async def handle_login(request: Request, email: str = Form(...), password: str = Form(...)):
    # Pydantic Validation
    try:
        user_data = AuthSchema(email=email, password=password)
        # Proceed with Supabase/Auth logic
        return {"status": "success"}
    except Exception as e:
        return templates.TemplateResponse("auth/_signin.html", {
            "request": request, 
            "error": str(e)
        })