from fastapi import APIRouter, Request
from config import templates  # Humari config file se

router = APIRouter()

# Note: Jinja2 mein 'request' pass karna zaroori hota hai
@router.get("/login") 
async def get_login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})