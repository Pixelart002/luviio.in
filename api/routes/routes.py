from fastapi import APIRouter

# Ye wahi 'router' hai jisko main.py import kar raha hai
router = APIRouter()



# --- ROUTES ---
@app.get("/", response_class=HTMLResponse)
async def home_route(request: Request):
    # No state needed – templates are static
    return templates.TemplateResponse(
        "app/pages/index.html", 
        {"request": request}
    )