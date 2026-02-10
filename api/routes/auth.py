from fastapi import APIRouter, Request, Header
from fastapi.responses import HTMLResponse

router = APIRouter()

# api/routes/auth.py

@router.get("/")
async def render_home(request: Request, x_up_target: str = Header(None)):
    return request.app.state.templates.TemplateResponse("app/pages/home.html", {
        "request": request,
        "title": "Home | LUVIIO",
        "up_fragment": x_up_target is not None,
        "active_page": "home",
        "nav_flags": {"sticky": True, "glass": True} # Ye miss mat karein
    })

# AGAR AAPNE WAITLIST PAGE BANAYA HAI, TOH USME BHI YE DAALEIN
@router.get("/waitlist")
async def render_waitlist(request: Request, x_up_target: str = Header(None)):
    return request.app.state.templates.TemplateResponse("app/pages/waitlist.html", {
        "request": request,
        "title": "Waitlist | LUVIIO",
        "up_fragment": x_up_target is not None,
        "active_page": "waitlist",
        "nav_flags": {"sticky": True, "glass": True}
    })