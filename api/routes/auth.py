from fastapi import APIRouter, Request, Header
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    # Global state se templates uthayein
    templates = request.app.state.templates
    
    context = {
        "request": request,
        "title": "Home | LUVIIO",
        "up_fragment": x_up_target is not None, # Unpoly flag
        "active_page": "home"
    }
    
    # Path based on your folder structure:
    # api/templates/app/pages/home.html
    return templates.TemplateResponse("app/pages/home.html", context)