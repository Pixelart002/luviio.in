from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# FIX: Relative import. 'from .routers' means "look in the same folder as this file for a routers folder"
from .routers import public 

app = FastAPI(title="Luviio Platform", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(public.router)

@app.on_event("startup")
async def startup_event():
    print("Luviio Engine: INITIALIZED")