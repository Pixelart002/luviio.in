"""
Supabase Client — Stateless & Thread-Safe Factory (Sync & Async)
================================================================
Path: app/core/supabase.py

Architecture & Fixes:
  ✅ Prevents Auth Session Bleeding — Regular client is fetched statelessly/on-demand.
  ✅ Thread-Safe Admin — Admin (service-role) clients are safely pooled as singletons.
  ✅ Zero Session Collision — Solves the "Admin session appearing for unlogged users" bug.
"""
import logging
from typing import Optional
from supabase import create_client, create_async_client, Client, AsyncClient, ClientOptions
from gotrue import AsyncMemoryStorage
from app.core.config import settings

logger = logging.getLogger(__name__)

# Admin clients can be singletons since they bypass RLS/Auth sessions
_admin_supabase: Optional[Client] = None
_async_admin_supabase: Optional[AsyncClient] = None
_initialized_admins = False


async def init_admin_clients() -> None:
    """
    Initialize only Admin (Service Role) clients globally.
    Regular auth clients should be created per-request to avoid session pollution.
    """
    global _admin_supabase, _async_admin_supabase, _initialized_admins
    if _initialized_admins:
        return

    if not settings.SB_URL or not settings.SB_KEY or not settings.SB_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase credentials missing.")

    try:
        opts = ClientOptions(auto_refresh_token=False)
        async_opts = ClientOptions(auto_refresh_token=False, storage=AsyncMemoryStorage())
        
        # Admin clients (No user session persistence needed)
        _admin_supabase = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=opts)
        _async_admin_supabase = await create_async_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=async_opts)
        
        _initialized_admins = True
        logger.info("✅ Supabase Admin (Service Role) clients initialized successfully")
    except Exception as exc:
        raise RuntimeError(f"Supabase admin connection failed: {exc}") from exc


# ── REGULAR CLIENTS (On-Demand / Stateless) ──────────────────────────────────

def get_supabase() -> Client:
    """
    Returns a fresh, stateless sync client for standard operations.
    Prevents session contamination across concurrent requests.
    """
    if not settings.SB_URL or not settings.SB_KEY:
        raise RuntimeError("Supabase credentials missing.")
    
    opts = ClientOptions(auto_refresh_token=False)
    return create_client(settings.SB_URL, settings.SB_KEY, options=opts)


async def get_async_supabase_on_demand() -> AsyncClient:
    """
    Returns a fresh async client per-request with its own isolated memory storage.
    CRITICAL: This stops the 'Admin auto-login' bug for anonymous HTTP requests.
    """
    if not settings.SB_URL or not settings.SB_KEY:
        raise RuntimeError("Supabase credentials missing.")
    
    async_opts = ClientOptions(auto_refresh_token=False, storage=AsyncMemoryStorage())
    return await create_async_client(settings.SB_URL, settings.SB_KEY, options=async_opts)


# ── ADMIN CLIENTS (Singletons) ──────────────────────────────────────────────

def get_admin_supabase() -> Client:
    """Returns the globally shared Sync Admin Client."""
    if not _initialized_admins:
        # Fallback inline initialization if not called in lifespan
        opts = ClientOptions(auto_refresh_token=False)
        return create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=opts)
    return _admin_supabase


async def get_async_admin_supabase() -> AsyncClient:
    """Returns the globally shared Async Admin Client."""
    if not _initialized_admins:
        await init_admin_clients()
    return _async_admin_supabase