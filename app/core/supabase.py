"""
Supabase Client — Thread-Safe Singleton
========================================
Architecture Layer: Core Infrastructure (app/core/supabase.py)
Pattern: Singleton with double-checked locking

LLD Concepts Applied:
  Singleton Pattern      → single instance per process
  Thread Safety          → threading.Lock prevents concurrent init
  Atomic Swap            → both clients created before assigning to globals
  Lazy Initialization    → auto-init on first getter call (defensive)
  Fail-Fast              → missing credentials → immediate RuntimeError
"""
import threading
import logging
from typing import Optional

from supabase import create_client, Client, ClientOptions

# 🔥 ARCHITECTURE CHANGE: Settings now comes from the 'core' module
from app.core.config import settings

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
#  GLOBAL STATE (Process-Level Singletons)
# ══════════════════════════════════════════════════════════════════════════════

_supabase: Optional[Client] = None
_admin_supabase: Optional[Client] = None
_lock = threading.Lock()
_initialized = False

# ══════════════════════════════════════════════════════════════════════════════
#  INITIALIZATION (Called once at startup)
# ══════════════════════════════════════════════════════════════════════════════

def init_clients() -> None:
    global _supabase, _admin_supabase, _initialized

    if _initialized and _supabase is not None:
        logger.debug("Supabase clients already initialized — skipping")
        return

    with _lock:
        if _initialized and _supabase is not None:
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

            regular_client = create_client(settings.SB_URL, settings.SB_KEY, options=_client_options)
            logger.debug("Regular Supabase client created (RLS enabled)")

            admin_client = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=_client_options)
            logger.debug("Admin Supabase client created (RLS bypass)")

            _supabase = regular_client
            _admin_supabase = admin_client
            _initialized = True

            logger.info("✅ Supabase clients initialized successfully")

        except Exception as exc:
            logger.critical("Failed to initialize Supabase clients: %s", exc, exc_info=True)
            raise RuntimeError(f"Supabase connection failed: {exc}") from exc

# ══════════════════════════════════════════════════════════════════════════════
#  GETTERS
# ══════════════════════════════════════════════════════════════════════════════

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

def is_connected() -> bool:
    return _initialized and _supabase is not None and _admin_supabase is not None

def reset_clients() -> None:
    global _supabase, _admin_supabase, _initialized
    with _lock:
        _supabase = None
        _admin_supabase = None
        _initialized = False
    logger.info("Supabase clients reset")