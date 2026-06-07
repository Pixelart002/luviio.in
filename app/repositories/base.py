"""
Base Repository Pattern
========================
Architecture Layer: Data Access Layer
Path: app/repositories/base.py
"""
import logging
from app.core.supabase import get_supabase, get_admin_supabase

logger = logging.getLogger(__name__)

class BaseRepository:
    """
    Base Repository class.
    Provides standard and admin database clients to all child repositories.
    """
    def __init__(self):
        # Regular client (respects RLS)
        self.sb = get_supabase()
        
        # Admin client (bypasses RLS - use with caution!)
        self.admin_sb = get_admin_supabase()