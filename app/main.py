from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from app.middleware.security import rate_limiter, csrf_protect
from app.db.client import supabase_client
from app.ecommerce import products, cart, checkout

import os

app = FastAPI(title="Luviio E-Commerce", version="1.0")

# Static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Middleware
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET", "supersecret"))

app.middleware("http")(rate_limiter)
app.middleware("http")(csrf_protect)

# Routes
app.include_router(products.router, prefix="/products", tags=["Products"])
app.include_router(cart.router, prefix="/cart", tags=["Cart"])
app.include_router(checkout.router, prefix="/checkout", tags=["Checkout"])

# Home Route
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    product_list = await products.get_all_products()
    return templates.TemplateResponse("home.html", {"request": request, "products": product_list})