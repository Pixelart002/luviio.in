from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os

app = FastAPI()

# Static files (optional)
app.mount("/static", StaticFiles(directory="../static"), name="static")

# Templates folder
templates = Jinja2Templates(directory="../templates")  # <- templates folder at project root

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(
        "/home.html",  # <- exact file name in templates folder
        {
            "request": request,   # mandatory
            "user_name": "Anya",
            "items": ["Apple", "Banana", "Cherry"]
        }
    )