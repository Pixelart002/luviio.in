import os
from fastapi import APIRouter, Request, Header
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

router = APIRouter()

# Path set karein (api folder ke andar)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@router.get("/", response_class=HTMLResponse)
async def get_home(request: Request, x_up_target: str = Header(None)):
    """
    Unpoly Integration: Agar 'X-Up-Target' header hai, 
    toh hum poora layout nahi bhejenge.
    """
    context = {"request": request, "title": "Luviio Portal"}
    
    # Unpoly Fragment handling
    if x_up_target == "#main-content":
        return templates.TemplateResponse("/layout-components/login_macros.html", context)
        
    # Default: Poora page serve karein
    return templates.TemplateResponse("active-layouts/index.html", context)

@router.post("/api/v1/update-profile")
@db_safe_execute
async def update_profile(request: Request, x_up_target: str = Header(None)):
    form_data = await request.form()
    # Supabase update call
    supabase.table("profiles").update({
        "full_name": form_data.get("full_name"),
        "bio": form_data.get("bio")
    }).eq("id", "current-user-id").execute()

    # Unpoly Fragment Response
    if x_up_target == "#profile-section":
        # Sirf update hua card wapas bhejein
        user_data = {"full_name": form_data.get("full_name"), "bio": form_data.get("bio")}
        return templates.TemplateResponse("macros/page-specific/profile_macros.html", 
                                       {"request": request, "user": user_data})