from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse
import logging

logger = logging.getLogger(__name__)

async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception", exc_info=exc)
    # If the client expects HTML (e.g., browser navigation), return a friendly error page
    if "text/html" in request.headers.get("accept", ""):
        return HTMLResponse(
            content="<h1>Something went wrong</h1><p>Our team has been notified.</p>",
            status_code=500
        )
    # Otherwise return JSON
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )