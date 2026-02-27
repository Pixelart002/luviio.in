import os
import sys

# Vercel Path Fix - Sabse Upar
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from fastapi import FastAPI
from api.routes.pages import router as pages_router

app = FastAPI(title="Luviio Modular")

# Include Routers
app.include_router(pages_router)