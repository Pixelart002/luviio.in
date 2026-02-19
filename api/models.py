from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class LinkItem(BaseModel):
    label: str
    url: str
    active: bool = False

class FooterSection(BaseModel):
    title: str
    links: List[LinkItem]

class UIState(BaseModel):
    page_title: str
    nav_items: List[LinkItem]
    sidebar_categories: List[LinkItem]
    footer_sections: List[FooterSection]
    featured_material: Optional[Dict[str, str]] = None
    user_status: str = "Studio Access"
    server_time: str = datetime.now().strftime("%H:%M:%S")
    meta_tags: Optional[Dict[str, str]] = None   # For SEO