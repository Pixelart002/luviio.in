"""
Base Repository Pattern
========================
Architecture Layer: Data Access Layer
Path: app/repositories/base.py

Architecture & Fixes:
  ✅ Stateless Execution — Provides helper methods to fetch clients on-demand safely.
  ✅ Resolves Coroutine Crash — Removes synchronous execution assignments from constructor.
"""
import logging
from app.core.supabase import get_supabase, get_admin_supabase, get_async_supabase, get_async_admin_supabase

logger = logging.getLogger(__name__)

class BaseRepository:
    """
    Base Repository class.
    Provides standard and admin database clients to all child repositories statelessly.
    """
    def __init__(self):
        # Synchronous client properties are initialized directly
        self.sb = get_supabase()
        self.admin_sb = get_admin_supabase()

    async def get_async_client(self):
        """Returns the async regular client (respects RLS) on-demand."""
        return await get_async_supabase()

    async def get_async_admin_client(self):
        """Returns the async admin client (bypasses RLS) on-demand."""
        return await get_async_admin_supabase()