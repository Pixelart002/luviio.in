import os
from fastapi.templating import Jinja2Templates
from api.config.settings import UI_CONFIG

# Vercel-proof path resolution
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")

# Initialize Jinja
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# INJECT CONFIG GLOBALLY (Magic happens here)
templates.env.globals['ui_config'] = UI_CONFIG