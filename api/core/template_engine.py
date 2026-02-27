import os
from fastapi.templating import Jinja2Templates
from api.config.settings import UI_CONFIG

# ==========================================
# 🔥 SMART VERCEL-PROOF PATH RESOLUTION
# ==========================================
# __file__ ka matlab hai api/core/template_engine.py
CORE_DIR = os.path.dirname(os.path.abspath(__file__)) 
API_DIR = os.path.dirname(CORE_DIR)  # Yeh ban gaya 'api/' folder

# Pehla Try: 'api/templates' (Kyunki Vercel pe yahi bachega)
TEMPLATE_DIR = os.path.join(API_DIR, "templates")

# Backup Try: Agar galti se tumne folder root me hi chhod diya (Local testing)
if not os.path.exists(TEMPLATE_DIR):
    ROOT_DIR = os.path.dirname(API_DIR)
    TEMPLATE_DIR = os.path.join(ROOT_DIR, "templates")

# ==========================================
# INITIALIZE & INJECT
# ==========================================
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# INJECT CONFIG GLOBALLY (Ab ui_config har page ko apne aap mil jayega!)
templates.env.globals['ui_config'] = UI_CONFIG