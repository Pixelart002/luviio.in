"""
Supabase client — Thread-Safe Singleton Pattern
================================================
Pattern: Singleton with double-checked locking
Why: Multiple uvicorn workers + startup race = potential partial-init

LLD concept applied:
  Singleton     → single instance per process
  Thread Safety → threading.Lock prevents concurrent init
  Atomic swap   → both clients created before assigning to globals
"""
import threading
import logging
from typing import Optional
from supabase import create_client, Client
from app.config import settings

logger = logging.getLogger(__name__)

# Global instances
_supabase: Optional[Client] = None
_admin_supabase: Optional[Client] = None
_lock = threading.Lock()  # Thread safety — double-checked locking


def init_clients() -> None:
    """
    Called once at app startup (lifespan).
    Double-checked locking — thread-safe singleton init.
    Atomic swap: both clients built in temp vars before assignment.
    """
    global _supabase, _admin_supabase

    if _supabase is not None:  # Fast path — no lock needed after init
        return

    with _lock:
        if _supabase is not None:  # Second check inside lock
            return
        
        # Guard: Ensure credentials exist before calling create_client
        if not settings.SB_URL or not settings.SB_KEY:
            logger.critical("Supabase credentials missing! Check your .env file.")
            raise RuntimeError("SB_URL or SB_KEY is not set in environment.")

        try:
            # Build in temp vars — partial init protection (Atomic Swap)
            _sb = create_client(settings.SB_URL, settings.SB_KEY)
            
            # Use Service Role Key for Admin client (Bypass RLS)
            _admin = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY)
            
            # Atomic assignment to globals
            _supabase = _sb
            _admin_supabase = _admin
            
            logger.info("Supabase clients (Regular & Admin) initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase clients: {e}")
            raise


def get_supabase() -> Client:
    """Getter for the regular client (respects RLS)."""
    if _supabase is None:
        # Auto-init attempt if not initialized (defensive)
        init_clients()
        if _supabase is None:
            raise RuntimeError("Supabase regular client not initialised.")
    return _supabase


def get_admin_supabase() -> Client:
    """Getter for the admin client (bypasses RLS)."""
    if _admin_supabase is None:
        # Auto-init attempt if not initialized (defensive)
        init_clients()
        if _admin_supabase is None:
            raise RuntimeError("Supabase admin client not initialised.")
    return _admin_supabase