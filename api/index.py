import os
import sys

# 1. Get the current directory (api/)
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. Get the parent directory (project root where 'app/' lives)
parent_dir = os.path.dirname(current_dir)

# 3. Inject the parent directory into sys.path
sys.path.append(parent_dir)

# 4. Now import the app
from app.main import app

# This is required for Vercel to find the entry point
# No other code is needed here.