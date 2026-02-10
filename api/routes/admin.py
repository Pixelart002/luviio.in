import os
from fastapi import APIRouter, Request, Header
from fastapi.templating import Jinja2Templates
from .database import supabase, db_safe_execute #

router = APIRouter(prefix="/admin", tags=["Admin"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/dashboard")
@db_safe_execute
async def admin_dashboard(request: Request, x_up_target: str = Header(None)):
    # Mock Data (Asli dashboard mein Supabase queries aayengi)
    context = {
        "request": request,
        "up_fragment": x_up_target == "#main-content", # Check if it's a partial update
        "stats": {
            "revenue": "₹8,42,000",
            "users": "14,201",
            "orders": "482"
        },
        "recent_orders": [
            {"id": "LUV-8821", "customer": "Aman Verma", "status": "Paid", "status_color": "success", "amount": "₹4,200"},
            {"id": "LUV-8822", "customer": "Sneha Roy", "status": "Pending", "status_color": "warning", "amount": "₹1,150"},
            {"id": "LUV-8823", "customer": "John Doe", "status": "Shipped", "status_color": "info", "amount": "₹8,900"}
        ]
    }
    
    # Unpoly Fragment Logic
    return templates.TemplateResponse("pages/dashboard_home.html", context)