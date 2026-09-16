"""
Supabase Client — Stateless & Thread-Safe Factory (Sync & Async)
================================================================
Path: app/core/supabase.py

Architecture & Fixes:
  Prevents Auth Session Bleeding — Regular client is fetched statelessly/on-demand.
  Thread-Safe Admin — Admin (service-role) clients are safely pooled as singletons.
  Zero Session Collision — Solves the "Admin session appearing for unlogged users" bug.
  Backward Compatibility — Retains `get_async_supabase` alias to prevent ImportError crashes.
"""
import logging
from typing import Optional

from supabase import AsyncClient, Client, ClientOptions, create_async_client, create_client

from app.core.config import settings

logger = logging.getLogger(__name__)

_admin_supabase: Optional[Client] = None
_async_admin_supabase: Optional[AsyncClient] = None
_initialized_admins = False


async def init_admin_clients() -> None:
    """Initialize only Admin (Service Role) clients globally."""
    global _admin_supabase, _async_admin_supabase, _initialized_admins
    if _initialized_admins:
        return

    if not settings.SB_URL or not settings.SB_KEY or not settings.SB_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase credentials missing.")

    try:
        opts = ClientOptions(auto_refresh_token=False, persist_session=False)
        async_opts = ClientOptions(auto_refresh_token=False, persist_session=False)

        _admin_supabase = create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=opts)
        _async_admin_supabase = await create_async_client(
            settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=async_opts
        )

        _initialized_admins = True
        logger.info("Supabase admin clients initialized | role=service_role")
    except Exception as exc:
        raise RuntimeError(f"Supabase admin connection failed: {exc}") from exc


# ── REGULAR CLIENTS (On-Demand / Stateless) ──────────────────────────────────

def get_supabase() -> Client:
    """Returns a fresh, stateless sync client for standard operations."""
    if not settings.SB_URL or not settings.SB_KEY:
        raise RuntimeError("Supabase credentials missing.")

    opts = ClientOptions(auto_refresh_token=False, persist_session=False)
    return create_client(settings.SB_URL, settings.SB_KEY, options=opts)


async def get_async_supabase_on_demand() -> AsyncClient:
    """Return a fresh async client that never persists an auth session."""
    if not settings.SB_URL or not settings.SB_KEY:
        raise RuntimeError("Supabase credentials missing.")

    # This is a backend request-scoped client. Persisting sessions is neither
    # required nor desirable here. In supabase-py, sign_in_with_password()
    # clears any existing session on authentication failure; with persistence
    # enabled that cleanup awaits storage.remove_item(). The default async
    # storage implementation in the pinned client can be absent/incompatible
    # in this server-side lifecycle, producing:
    #   TypeError: object NoneType can't be used in 'await' expression
    # Keep the client explicitly stateless so auth cleanup uses in-memory state.
    async_opts = ClientOptions(auto_refresh_token=False, persist_session=False)
    return await create_async_client(settings.SB_URL, settings.SB_KEY, options=async_opts)


# ── ADMIN CLIENTS (SINGLETONS) ──────────────────────────────────────────────

def get_admin_supabase() -> Client:
    """Returns the globally shared Sync Admin Client."""
    if not _initialized_admins:
        opts = ClientOptions(auto_refresh_token=False, persist_session=False)
        return create_client(settings.SB_URL, settings.SB_SERVICE_ROLE_KEY, options=opts)
    return _admin_supabase


async def get_async_admin_supabase() -> AsyncClient:
    """Returns the globally shared Async Admin Client."""
    if not _initialized_admins:
        await init_admin_clients()
    return _async_admin_supabase


# ── COMPATIBILITY ALIASES ───────────────────────────────────────────────────
get_async_supabase = get_async_supabase_on_demand
