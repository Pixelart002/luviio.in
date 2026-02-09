import os
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Sahi path set karne ke liye
# Ye line 'api' folder se bahar nikal kar root folder tak pahunchegi
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Static aur Templates ka rasta fix karein
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})