@router.get("/")
async def render_home(request: Request, x_up_target: str = Header(None)):
    templates = request.app.state.templates
    context = {
        "request": request,
        "title": "LUVIIO | Overview",
        "up_fragment": x_up_target is not None,
        "active_page": "home", # Nav items highlight karne ke liye
        "user": None, # Session logic yahan aayega
        "nav_flags": {"sticky": True, "glass": True} # Macro flags
    }
    return templates.TemplateResponse("app/pages/home.html", context)