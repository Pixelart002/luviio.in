import sys
import os

# BOILERPLATE: Add the parent directory (project root) to sys.path
# This fixes "ModuleNotFoundError: No module named 'app.routers'"
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))

from app.main import app

# Vercel requires the variable to be named 'app'
# This 'app' is the FastAPI instance imported above