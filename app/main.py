from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.routers import public

app = FastAPI(title="Luviio Platform", docs_url=None, redoc_url=None)

# Mount Static Files (CSS/JS)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include Routers
app.include_router(public.router)

@app.on_event("startup")
async def startup_event():
    print("Luviio Engine: INITIALIZED")