import sys
import os

# --- THE FIX ---
# Get the directory where this script (api/index.py) is located
current_dir = os.path.dirname(os.path.abspath(__file__))
# Get the parent directory (project root)
parent_dir = os.path.dirname(current_dir)

# Add the parent directory to sys.path so Python can find the 'app' folder
sys.path.append(parent_dir)
# ---------------

# Now we can safely import the app
from app.main import app

# Handler for Vercel Serverless (required for some older runtimes, but good safety)
# Usually 'app' object is enough, but this is explicit.
handler = app