"""
Supabase Client — Thread-Safe Singleton (Sync & Async)
======================================================
Path: app/core/supabase.py

BUG FIX: `create_async_client` is an async function in supabase-py. 
It MUST be awaited during initialization.
"""
import logging
from typing import Optional
from supabase import create_client, create_async_client, Client, AsyncClient, ClientOptions
from app.core.config import settings

logger = logging.getLogger(__name__)

_supabase: Optional[Client] = None
_admin_supabase: Optional[Client] = None
_async_supabase: Optional[AsyncClient] = None
_async_admin_supabase: Optional[AsyncClient] = None
_initialized = False

async def init_clients() -> None:
    """Initialize all Supabase clients asynchronously. Must be awaited in Lifespan."""
    global _supabase, _admin_supabase, _async_supabase, _async_admin_supabase, _initialized
    if _initialized: return

    if not settings.SB_URL or not settings.SB_KEY or not settings.SB_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase credentials missing.")

    try:
        opts = ClientOptions(auto_refresh_token=False)
        
        # 1. Sync Clients
        _supabase = create_client(settings.SB_URL, settings.SB_KEY, options=opts)
        _admin_supabase = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=opts)
        
        # 2. Async Clients (🔥 FIXED: Now properly awaited!)
        _async_supabase = await create_async_client(settings.SB_URL, settings.SB_KEY, options=opts)
        _async_admin_supabase = await create_async_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=opts)
        
        _initialized = True
        logger.info("✅ All Supabase clients (Sync & Async) initialized successfully")
    except Exception as exc:
        raise RuntimeError(f"Supabase connection failed: {exc}") from exc

def get_supabase() -> Client:
    if not _initialized: raise RuntimeError("Supabase not initialized.")
    return _supabase

def get_admin_supabase() -> Client:
    if not _initialized: raise RuntimeError("Supabase not initialized.")
    return _admin_supabase

def get_async_supabase() -> AsyncClient:
    if not _initialized: raise RuntimeError("Supabase not initialized.")
    return _async_supabase

def get_async_admin_supabase() -> AsyncClient:
    if not _initialized: raise RuntimeError("Supabase not initialized.")
    return _async_admin_supabase