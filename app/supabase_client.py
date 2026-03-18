"""
Supabase client — Thread-Safe Singleton Pattern
================================================
Pattern: Singleton with double-checked locking
Why: Multiple uvicorn workers + startup race = potential partial-init

LLD concept applied:
  Singleton  → single instance per process
  Thread Safety → threading.Lock prevents concurrent init
  Atomic swap → both clients created before assigning to globals
"""
import threading
from supabase import create_client, Client
from app.config import settings

_supabase: Client | None = None
_admin_supabase: Client | None = None
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
        # Build in temp vars — partial init protection
        _sb    = create_client(settings.SB_URL, settings.SB_KEY)
        _admin = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY)
        _supabase, _admin_supabase = _sb, _admin  # Atomic assignment


def get_supabase() -> Client:
    if _supabase is None:
        raise RuntimeError("Supabase not initialised — call init_clients() first")
    return _supabase


def get_admin_supabase() -> Client:
    if _admin_supabase is None:
        raise RuntimeError("Supabase admin not initialised — call init_clients() first")
    return _admin_supabase