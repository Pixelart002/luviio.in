@router.get("/", response_class=HTMLResponse)
async def render_home(request: Request, x_up_target: str = Header(None)):
    templates = request.app.state.templates
    context = {
        "request": request,
        "title": "Home | LUVIIO",
        "up_fragment": x_up_target is not None,
        "active_page": "home", # Ye header macro read karega
        "user": None # Future mein Supabase session yahan jayega
    }
    return templates.TemplateResponse("app/pages/home.html", context)