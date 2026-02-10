from fastapi import APIRouter, Request, Header
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    # request.app.state se templates uthayein (jo main.py mein define kiya tha)
    templates = request.app.state.templates
    
    context = {
        "request": request,
        "title": "Home | LUVIIO",
        "up_fragment": x_up_target is not None,
        "active_page": "home"
    }
    
    # PATH FIX: 'app/pages/home.html' likhna zaroori hai
    return templates.TemplateResponse("app/pages/home.html", context)