import os
from fastapi import APIRouter, Request, Header
from fastapi.templating import Jinja2Templates
from .database import supabase, db_safe_execute #

router = APIRouter(prefix="/admin", tags=["Admin"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/dashboard")
@db_safe_execute
async def admin_dashboard(request: Request):
    # 1. DB Connection Check: Ek simple query run karein
    # Maan lijiye aapke pass 'profiles' ya 'settings' table hai
    db_check = supabase.table("profiles").select("count", count="exact").limit(1).execute()
    
    # Agar ye line execute ho gayi, matlab DB connected hai
    stats = {
        "status": "Online",
        "db_connected": True,
        "total_users": db_check.count if db_check.count else 0
    }

    context = {
        "request": request,
        "stats": stats,
        "user": {"name": "Senior Admin"},
        "active_page": "dashboard"
    }
    
    return templates.TemplateResponse("admin/dashboard.html", context)