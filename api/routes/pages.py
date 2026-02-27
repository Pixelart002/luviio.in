from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from api.core.template_engine import templates
from api.db.database import get_db, get_admin_db

router = APIRouter()



db = get_db()
admin_db = get_admin_db()




@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    # Sirf Request aur User data bhejna hai, Config automatically chala jayega
    current_user = getattr(request.state, "user", None)
    return templates.TemplateResponse("pages/index.html", {
        "request": request,
        "user": current_user
    })