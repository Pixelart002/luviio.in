from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class UIState(BaseModel):
    page_title: str
    nav_items: List[Dict[str, Any]]
    sidebar_categories: List[Dict[str, Any]]
    footer_sections: List[Dict[str, Any]]
    featured_material: Optional[Dict[str, Any]] = None
    featured_materials: List[Dict[str, Any]] = []
    user_status: str = "Studio Access"
    footer_about: Optional[str] = None