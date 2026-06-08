"""
Supabase Client — Thread-Safe Singleton (Sync & Async)
======================================================
Architecture Layer: Core Infrastructure (app/core/supabase.py)
Pattern: Singleton with double-checked locking

LLD Concepts Applied:
  Singleton Pattern      → single instance per process
  Thread Safety          → threading.Lock prevents concurrent init
  Async Pooling          → non-blocking httpx connections for FastAPI
  Lazy Initialization    → auto-init on first getter call (defensive)
  Fail-Fast              → missing credentials → immediate RuntimeError
"""
import threading
import logging
from typing import Optional

# 🔥 Brought in AsyncClient and create_async_client for 10x performance
from supabase import create_client, create_async_client, Client, AsyncClient, ClientOptions

from app.core.config import settings

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  GLOBAL STATE (Process-Level Singletons)
# ══════════════════════════════════════════════════════════════════════════════

# Sync Clients (Legacy / Background threads)
_supabase: Optional[Client] = None
_admin_supabase: Optional[Client] = None

# Async Clients (FastAPI non-blocking)
_async_supabase: Optional[AsyncClient] = None
_async_admin_supabase: Optional[AsyncClient] = None

_lock = threading.Lock()
_initialized = False

# ══════════════════════════════════════════════════════════════════════════════
#  INITIALIZATION (Called once at startup in Lifespan)
# ══════════════════════════════════════════════════════════════════════════════

def init_clients() -> None:
    global _supabase, _admin_supabase, _async_supabase, _async_admin_supabase, _initialized

    if _initialized:
        logger.debug("Supabase clients already initialized — skipping")
        return

    with _lock:
        if _initialized:
            return

        if not settings.SB_URL:
            raise RuntimeError("SB_URL is not set.")
        if not settings.SB_KEY:
            raise RuntimeError("SB_KEY is not set.")
        if not settings.SB_SERVICE_ROLE_KEY:
            raise RuntimeError("SB_SERVICE_ROLE_KEY is not set.")

        logger.info(
            "Initializing Supabase clients | url=%s",
            settings.SB_URL[:30] + "..." if len(settings.SB_URL) > 30 else settings.SB_URL
        )

        try:
            _client_options = ClientOptions(auto_refresh_token=False)

            # 1. Initialize Sync Clients
            _supabase = create_client(settings.SB_URL, settings.SB_KEY, options=_client_options)
            _admin_supabase = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=_client_options)
            logger.debug("Sync Supabase clients created.")

            # 2. Initialize Async Clients (For extreme performance)
            _async_supabase = create_async_client(settings.SB_URL, settings.SB_KEY, options=_client_options)
            _async_admin_supabase = create_async_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=_client_options)
            logger.debug("Async Supabase clients created.")

            _initialized = True
            logger.info("✅ All Supabase clients (Sync & Async) initialized successfully")

        except Exception as exc:
            logger.critical("Failed to initialize Supabase clients: %s", exc, exc_info=True)
            raise RuntimeError(f"Supabase connection failed: {exc}") from exc

# ══════════════════════════════════════════════════════════════════════════════
#  GETTERS
# ══════════════════════════════════════════════════════════════════════════════

# ── SYNC GETTERS ──────────────────────────────────────────────────────────────

def get_supabase() -> Client:
    if _supabase is None:
        logger.warning("Regular client not initialized — auto-initializing")
        init_clients()
        if _supabase is None:
            raise RuntimeError("Supabase regular client could not be initialized.")
    return _supabase

def get_admin_supabase() -> Client:
    if _admin_supabase is None:
        logger.warning("Admin client not initialized — auto-initializing")
        init_clients()
        if _admin_supabase is None:
            raise RuntimeError("Supabase admin client could not be initialized.")
    return _admin_supabase


# ── ASYNC GETTERS (Use these in FastAPI async routes for speed!) ─────────────

def get_async_supabase() -> AsyncClient:
    if _async_supabase is None:
        logger.warning("Async regular client not initialized — auto-initializing")
        init_clients()
        if _async_supabase is None:
            raise RuntimeError("Supabase async regular client could not be initialized.")
    return _async_supabase

def get_async_admin_supabase() -> AsyncClient:
    if _async_admin_supabase is None:
        logger.warning("Async admin client not initialized — auto-initializing")
        init_clients()
        if _async_admin_supabase is None:
            raise RuntimeError("Supabase async admin client could not be initialized.")
    return _async_admin_supabase


# ── UTILITIES ─────────────────────────────────────────────────────────────────

def is_connected() -> bool:
    return _initialized and _supabase is not None and _async_supabase is not None

def reset_clients() -> None:
    global _supabase, _admin_supabase, _async_supabase, _async_admin_supabase, _initialized
    with _lock:
        _supabase = None
        _admin_supabase = None
        _async_supabase = None
        _async_admin_supabase = None
        _initialized = False
    logger.info("Supabase clients reset")