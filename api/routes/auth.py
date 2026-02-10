from fastapi import APIRouter, Request, Header

router = APIRouter()

@router.get("/")
async def render_home(request: Request, x_up_target: str = Header(None)):
    context = {
        "request": request,
        "title": "Home Page",
        "up_fragment": x_up_target is not None # Unpoly logic
    }
    # Path relative to 'api/templates'
    return templates.TemplateResponse("pages/home.html", context)