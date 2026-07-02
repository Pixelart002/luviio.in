import math
from typing import Any, List
from app.utils.response import success_response, PaginationMeta

def paginate(items: List[Any], total: int, page: int, page_size: int) -> dict:
    """
    Calculates pagination metadata and returns a standardized response.
    """
    if page_size <= 0:
        page_size = 20
    if page < 1:
        page = 1
        
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    
    meta = PaginationMeta(
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_previous=page > 1
    )
    
    return success_response(data=items, meta=meta)