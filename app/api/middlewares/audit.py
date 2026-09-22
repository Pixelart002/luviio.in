"""Persist a bounded audit trail for authenticated administrative mutations."""
import time
from uuid import UUID

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging_config import request_id_ctx
from app.core.supabase import get_async_admin_supabase


class AdminAuditMiddleware(BaseHTTPMiddleware):
    MUTATING = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        path = request.url.path
        if request.method in self.MUTATING and path.startswith("/api/v1/") and not path.endswith("/webhook"):
            actor_user_id = getattr(request.state, "user_id", None)
            try:
                actor_user_id = str(UUID(str(actor_user_id))) if actor_user_id else None
            except (ValueError, TypeError, AttributeError):
                actor_user_id = None
            try:
                sb = await get_async_admin_supabase()
                await sb.table("audit_logs").insert(
                    {
                        "request_id": request_id_ctx.get(),
                        "actor_user_id": actor_user_id,
                        "method": request.method,
                        "path": path[:500],
                        "status_code": response.status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                    }
                ).execute()
            except Exception:
                # Audit failure must never break the business request.
                pass
        return response
