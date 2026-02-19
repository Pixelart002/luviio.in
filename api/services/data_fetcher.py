from api.services.supabase_client import get_supabase_client
from api.models import UIState, LinkItem, FooterSection
from typing import Optional
import logging

logger = logging.getLogger(__name__)

async def fetch_ui_state(page_name: str = "home") -> UIState:
    """
    Fetch all required data from Supabase tables and build UIState.
    Use service role if you need to bypass RLS (e.g., for admin pages).
    """
    client = get_supabase_client(use_service_role=False)  # anon key for public data
    try:
        # Example: fetch nav_items from a 'navigation' table
        nav_response = client.table("navigation").select("*").eq("page", page_name).execute()
        nav_data = nav_response.data

        # Transform to LinkItem list
        nav_items = [
            LinkItem(label=item["label"], url=item["url"], active=item.get("active", False))
            for item in nav_data
        ]

        # Fetch sidebar categories from 'sidebar' table
        sidebar_response = client.table("sidebar").select("*").order("position").execute()
        sidebar_categories = [
            LinkItem(label=item["label"], url=item["url"])
            for item in sidebar_response.data
        ]

        # Fetch footer sections with nested links (maybe from a 'footer_sections' table)
        footer_response = client.table("footer_sections").select("*, footer_links(*)").execute()
        footer_sections = []
        for sec in footer_response.data:
            links = [LinkItem(label=link["label"], url=link["url"]) for link in sec.get("footer_links", [])]
            footer_sections.append(FooterSection(title=sec["title"], links=links))

        # Featured material
        featured = client.table("featured_material").select("*").limit(1).execute()
        featured_material = featured.data[0] if featured.data else None

        # Meta tags for SEO
        meta_response = client.table("meta_tags").select("*").eq("page", page_name).execute()
        meta_tags = meta_response.data[0] if meta_response.data else {}

        return UIState(
            page_title=meta_tags.get("title", "Luviio"),
            nav_items=nav_items,
            sidebar_categories=sidebar_categories,
            footer_sections=footer_sections,
            featured_material=featured_material,
            meta_tags=meta_tags,
            # user_status could be fetched from a user table if logged in
        )
    except Exception as e:
        logger.exception("Failed to fetch UI state from Supabase")
        # Return a fallback minimal state so the page still renders
        return UIState(
            page_title="Luviio",
            nav_items=[],
            sidebar_categories=[],
            footer_sections=[],
        )