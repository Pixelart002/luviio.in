from fastapi import APIRouter, Request  # 1. Request ko import karna zaroori hai
from config import templates            # 2. Humari config file se templates laayein

router = APIRouter()

@router.get("/login")
def login_page(request: Request):       # 3. Parameter mein 'request' lena padta hai
    # 4. JSON ki jagah ab hum TemplateResponse return karenge
    return templates.TemplateResponse("login.html", {"request": request})