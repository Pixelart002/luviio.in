"""
Pure & Colored Terminal Logger Middleware (FINAL)
=====================================================
Structured ASCII request logger with LUVIIO branding.
"""

import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


# ── ANSI Terminal Colors ──
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"

    BLUE = "\033[94m"
    DEEP_BLUE = "\033[34m"


# ── Silence Uvicorn Access Logs ──
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


class PureWindowLoggerMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next):

        # ── Skip noise routes ──
        if request.method == "OPTIONS" or request.url.path in ["/health", "/metrics"]:
            return await call_next(request)

        start_time = time.time()

        # ── Default request state ──
        request.state.user_name = "Guest (Unauthenticated)"
        request.state.user_id = "N/A"
        request.state.actions = []

        # ── Network info ──
        client_ip = request.client.host if request.client else "Unknown IP"
        origin = request.headers.get("origin", "Direct/Unknown Origin")
        user_agent = request.headers.get("user-agent", "Unknown Client")

        if len(user_agent) > 42:
            user_agent = user_agent[:39] + "..."

        # ── Execute request ──
        response = await call_next(request)

        # ── Metrics ──
        process_time = (time.time() - start_time) * 1000
        status = response.status_code

        status_color = C.GREEN if status < 400 else C.RED
        status_icon = "✅" if status < 400 else "❌"

        # ── Actions rendering ──
        if request.state.actions:
            actions_text = "\n".join(
                f"{C.CYAN}│{C.RESET}  {C.MAGENTA}➔{C.RESET} {act}"
                for act in request.state.actions
            )
        else:
            actions_text = f"{C.CYAN}│{C.RESET}  {C.DIM}➔ (No actions recorded){C.RESET}"

        # ── LUVIIO ASCII HEADER ──
        ascii_title = f"""
{C.DEEP_BLUE}{C.BOLD}
██╗     ██╗   ██╗██╗   ██╗██╗██╗ ██████╗ 
██║     ██║   ██║██║   ██║██║██║██╔═══██╗
██║     ██║   ██║██║   ██║██║██║██║   ██║
██║     ██║   ██║╚██╗ ██╔╝██║██║██║   ██║
███████╗╚██████╔╝ ╚████╔╝ ██║██║╚██████╔╝
╚══════╝ ╚═════╝   ╚═══╝  ╚═╝╚═╝ ╚═════╝ 
            LUVIIO LOG SYSTEM
{C.RESET}
"""

        # ── Window ──
        window = f"""
{ascii_title}
{C.CYAN}┌─────────────────────────────────────────────────────────────┐{C.RESET}
{C.CYAN}│{C.RESET} 👤 {C.BOLD}{C.DEEP_BLUE}IDENTITY & NETWORK{C.RESET}
{C.CYAN}│{C.RESET}  ├─ Name   : {C.DEEP_BLUE}{request.state.user_name}{C.RESET}
{C.CYAN}│{C.RESET}  ├─ ID     : {C.DEEP_BLUE}{request.state.user_id}{C.RESET}
{C.CYAN}│{C.RESET}  ├─ IP     : {client_ip}
{C.CYAN}│{C.RESET}  ├─ Origin : {origin}
{C.CYAN}│{C.RESET}  └─ Client : {C.DIM}{user_agent}{C.RESET}
{C.CYAN}│{C.RESET}
{C.CYAN}│{C.RESET} 🌐 {C.BOLD}{C.DEEP_BLUE}REQUEST DETAILS{C.RESET}
{C.CYAN}│{C.RESET}  ├─ API    : {C.BOLD}{request.method}{C.RESET} {request.url.path}
{C.CYAN}│{C.RESET}  └─ Status : {status_color}{status_icon} {status}{C.RESET} | ⏱️ {C.DEEP_BLUE}{process_time:.2f}ms{C.RESET}
{C.CYAN}│{C.RESET}
{C.CYAN}│{C.RESET} 🛠️  {C.BOLD}{C.DEEP_BLUE}ACTIONS PIPELINE{C.RESET}
{actions_text}
{C.CYAN}└─────────────────────────────────────────────────────────────┘{C.RESET}
"""

        print(window)
        return response