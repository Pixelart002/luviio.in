# api/routes/auth.py
@router.get("/dashboard")
async def dashboard_view(request: Request):
    # Asli dashboard mein ye data Supabase se aayega
    context = {
        "request": request,
        "user": {"name": "Senior Dev"},
        "stats": {
            "revenue": "₹5,24,000",
            "growth": "+18%"
        },
        "orders": [
            {"id": "#8821", "name": "Aman Verma", "status": "Paid", "total": "₹4,200"},
            {"id": "#8822", "name": "Sneha Roy", "status": "Pending", "total": "₹1,500"}
        ]
    }
    return templates.TemplateResponse("active-layouts/dashboard.html", context)