import os
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Current file (main.py) ki location nikalne ke liye
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Agar templates folder 'api' ke bahar root mein hai toh:
# Path ko ek level up le jayein (.. use karke)
template_path = os.path.join(BASE_DIR, "..", "templates")
static_path = os.path.join(BASE_DIR, "..", "static")

templates = Jinja2Templates(directory=template_path)
app.mount("/static", StaticFiles(directory=static_path), name="static")

@app.get("/")
async def home(request: Request):
    # 'home.html' file 'templates' folder ke andar honi chahiye
    return templates.TemplateResponse("home.html", {"request": request, "title": "My Pixel Art"})