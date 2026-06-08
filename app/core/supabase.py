"""
Supabase Client — Thread-Safe Singleton (Sync & Async)
======================================================
Path: app/core/supabase.py
"""
import threading
import logging
from typing import Optional
from supabase import create_client, create_async_client, Client, AsyncClient, ClientOptions
from app.core.config import settings

logger = logging.getLogger(__name__)

_supabase: Optional[Client] = None
_admin_supabase: Optional[Client] = None
_async_supabase: Optional[AsyncClient] = None
_async_admin_supabase: Optional[AsyncClient] = None
_lock = threading.Lock()
_initialized = False

def init_clients() -> None:
    global _supabase, _admin_supabase, _async_supabase, _async_admin_supabase, _initialized
    if _initialized: return

    with _lock:
        if _initialized: return
        if not settings.SB_URL or not settings.SB_KEY or not settings.SB_SERVICE_ROLE_KEY:
            raise RuntimeError("Supabase credentials missing.")

        try:
            opts = ClientOptions(auto_refresh_token=False)
            _supabase = create_client(settings.SB_URL, settings.SB_KEY, options=opts)
            _admin_supabase = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=opts)
            _async_supabase = create_async_client(settings.SB_URL, settings.SB_KEY, options=opts)
            _async_admin_supabase = create_async_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=opts)
            _initialized = True
            logger.info("✅ All Supabase clients (Sync & Async) initialized successfully")
        except Exception as exc:
            raise RuntimeError(f"Supabase connection failed: {exc}") from exc

def get_supabase() -> Client:
    if _supabase is None: init_clients()
    return _supabase

def get_admin_supabase() -> Client:
    if _admin_supabase is None: init_clients()
    return _admin_supabase

def get_async_supabase() -> AsyncClient:
    if _async_supabase is None: init_clients()
    return _async_supabase

def get_async_admin_supabase() -> AsyncClient:
    if _async_admin_supabase is None: init_clients()
    return _async_admin_supabase