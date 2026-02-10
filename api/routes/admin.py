import os
from fastapi import APIRouter, Request, Header
from fastapi.templating import Jinja2Templates
from .database import supabase, db_safe_execute #

router = APIRouter(prefix="/admin", tags=["Admin"])

# Template Setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/dashboard")
@db_safe_execute
async def admin_dashboard(request: Request, x_up_target: str = Header(None)):
    """
    Main Dashboard Logic: Fetching real data from Supabase.
    """
    # 1. Total Revenue Fetch (Assuming 'orders' table has 'total_amount')
    revenue_res = supabase.table('orders').select('total_amount').execute()
    total_revenue = sum(item['total_amount'] for item in revenue_res.data) if revenue_res.data else 0

    # 2. Total Users Count (Exact count from 'profiles' table)
    users_res = supabase.table('profiles').select('*', count='exact').execute()
    total_users = users_res.count if users_res.count else 0

    # 3. Recent Orders (Last 5 orders with customer names)
    orders_res = supabase.table('orders').select('*, profiles(full_name)').order('created_at', desc=True).limit(5).execute()
    
    context = {
        "request": request,
        "up_fragment": x_up_target == "#main-content",
        "stats": {
            "revenue": f"₹{total_revenue:,}", # Formatted currency
            "users": total_users,
            "orders": len(revenue_res.data) if revenue_res.data else 0
        },
        "recent_orders": orders_res.data if orders_res.data else []
    }

    # Jinja2 logic: If Unpoly request, send partial; else send full layout
    return templates.TemplateResponse("pages/dashboard.html", context)