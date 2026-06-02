"""
Supabase Client — Thread-Safe Singleton
========================================
Pattern: Singleton with double-checked locking
Why: Multiple uvicorn workers + startup race = potential partial-init

LLD Concepts Applied:
  Singleton Pattern      → single instance per process
  Thread Safety          → threading.Lock prevents concurrent init
  Atomic Swap            → both clients created before assigning to globals
  Lazy Initialization    → auto-init on first getter call (defensive)
  Fail-Fast              → missing credentials → immediate RuntimeError

Usage:
  from app.supabase_client import get_supabase, get_admin_supabase
  
  sb = get_supabase()         # Regular client (respects RLS)
  admin_sb = get_admin_supabase()  # Admin client (bypasses RLS)
"""
import threading
import logging
from typing import Optional

from supabase import create_client, Client

from app.config import settings

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
    """
    Initialize Supabase clients at application startup.
    
    Thread Safety:
      • Double-checked locking pattern
      • Fast path (no lock) for already-initialized state
      • Atomic swap: temp vars → global assignment
    
    Called from: main.py lifespan (startup event)
    
    Raises:
      RuntimeError: If credentials are missing or connection fails
    """
    global _supabase, _admin_supabase, _initialized

    # ── Fast path: Already initialized ────────────────────────────────────────
    if _initialized and _supabase is not None:
        logger.debug("Supabase clients already initialized — skipping")
        return

    # ── Slow path: Initialize with lock ───────────────────────────────────────
    with _lock:
        # Double-check inside lock (another thread may have initialized)
        if _initialized and _supabase is not None:
            return

        # ── Validate credentials ──────────────────────────────────────────────
        if not settings.SB_URL:
            raise RuntimeError(
                "SB_URL is not set. Check your .env file or environment variables."
            )
        if not settings.SB_KEY:
            raise RuntimeError(
                "SB_KEY is not set. Check your .env file or environment variables."
            )
        if not settings.SB_SERVICE_ROLE_KEY:
            raise RuntimeError(
                "SB_SERVICE_ROLE_KEY is not set. Check your .env file or environment variables."
            )

        logger.info(
            "Initializing Supabase clients | url=%s",
            settings.SB_URL[:30] + "..." if len(settings.SB_URL) > 30 else settings.SB_URL
        )

        try:
            # ── Create clients in temp variables (Atomic Swap) ────────────────
            # This prevents partial initialization — if admin client fails,
            # regular client is NOT assigned to global either.
            
            regular_client = create_client(settings.SB_URL, settings.SB_KEY)
            logger.debug("Regular Supabase client created (RLS enabled)")

            admin_client = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY)
            logger.debug("Admin Supabase client created (RLS bypass)")

            # ── Atomic assignment to globals ──────────────────────────────────
            # Both clients are ready — now assign atomically
            _supabase = regular_client
            _admin_supabase = admin_client
            _initialized = True

            logger.info("✅ Supabase clients initialized successfully")

        except Exception as exc:
            logger.critical(
                "Failed to initialize Supabase clients: %s",
                exc, exc_info=True
            )
            raise RuntimeError(
                f"Supabase connection failed: {exc}"
            ) from exc


# ══════════════════════════════════════════════════════════════════════════════
#  GETTERS (With Defensive Auto-Init)
# ══════════════════════════════════════════════════════════════════════════════

def get_supabase() -> Client:
    """
    Get the regular Supabase client (respects Row Level Security).
    
    Use for: Public queries, authenticated user queries (RLS-scoped)
    
    Auto-initializes if not already done (defensive programming).
    """
    if _supabase is None:
        logger.warning("Regular client not initialized — auto-initializing")
        init_clients()
        if _supabase is None:
            raise RuntimeError(
                "Supabase regular client could not be initialized. "
                "Check SB_URL and SB_KEY in your configuration."
            )
    return _supabase


def get_admin_supabase() -> Client:
    """
    Get the admin Supabase client (bypasses Row Level Security).
    
    Use for: Server-side operations, admin endpoints, background jobs
    ⚠️  Never expose this client to the frontend or untrusted code.
    
    Auto-initializes if not already done (defensive programming).
    """
    if _admin_supabase is None:
        logger.warning("Admin client not initialized — auto-initializing")
        init_clients()
        if _admin_supabase is None:
            raise RuntimeError(
                "Supabase admin client could not be initialized. "
                "Check SB_URL and SB_SERVICE_ROLE_KEY in your configuration."
            )
    return _admin_supabase


# ══════════════════════════════════════════════════════════════════════════════
#  HEALTH CHECK HELPER
# ══════════════════════════════════════════════════════════════════════════════

def is_connected() -> bool:
    """
    Check if Supabase clients are properly initialized.
    Used by health check endpoint.
    """
    return _initialized and _supabase is not None and _admin_supabase is not None


def reset_clients() -> None:
    """
    Reset clients (useful for testing).
    Not for production use.
    """
    global _supabase, _admin_supabase, _initialized
    with _lock:
        _supabase = None
        _admin_supabase = None
        _initialized = False
    logger.info("Supabase clients reset")