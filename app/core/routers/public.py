from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates

# FIX: Use relative import to go up to core (..)
from ..core.supabase import SupabaseService 

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/")
async def landing_page(request: Request):
    return templates.TemplateResponse("pages/index.html", {
        "request": request,
        "page_title": "Luviio | Redefining Digital Physics"
    })

@router.post("/join-waitlist")
async def join_waitlist(email: str = Form(...)):
    db = SupabaseService.get_client()
    if db:
        # data, count = db.table('leads').insert({"email": email}).execute()
        pass
    return {"status": "success", "message": "Welcome to the future."}