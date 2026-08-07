"""
Maintenance Mode Gatekeeper (Global Middleware)
===============================================
Path: app/core/maintenance.py
"""
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, status
from fastapi.responses import JSONResponse
from app.services.settings.service import SettingsService

logger = logging.getLogger(__name__)

class MaintenanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        
        # ⚠️ Bypass Admin, Settings, and Auth routes so you don't lock yourself out!
        if path.startswith("/api/v1/settings") or path.startswith("/api/v1/admin") or path.startswith("/api/v1/auth"):
            return await call_next(request)

        try:
            settings_svc = SettingsService()
            setting = await settings_svc.get_by_key("maintenance_mode")
            val = setting.get("value")
            
            # JSONB safe check (Handles both boolean True and string "true")
            is_maintenance = val is True or str(val).strip().lower() == "true"

            if is_maintenance:
                # Sidha JSON response return kar do bina API ko hit kiye
                return JSONResponse(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    content={
                        "success": False, 
                        "detail": "Store is currently under maintenance. APIs and checkout are temporarily locked."
                    }
                )
        except Exception as e:
            # Agar error aaye (e.g., DB down), toh gracefully ignore karo taaki store crash na ho
            logger.error(f"Maintenance check failed: {e}")

        # Agar maintenance mode OFF hai, toh request ko aage jaane do (Cart me add hone do)
        return await call_next(request)