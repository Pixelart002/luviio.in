"""
API Standard Response Wrapper
=============================
Path: app/utils/response.py
"""
from typing import Any, Optional
from pydantic import BaseModel

class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool

def success_response(data: Any = None, message: str = "Success", meta: Optional[PaginationMeta] = None) -> dict:
    """
    Standard wrapper for all successful API responses.
    This dict structure completely avoids Pydantic Generic[T] OpenAPI crash issues.
    """
    response = {
        "success": True,
        "message": message
    }
    if data is not None:
        response["data"] = data
    if meta is not None:
        response["meta"] = meta.model_dump()
        
    return response

def error_response(code: str, message: str, details: Any = None) -> dict:
    """Standard wrapper for all failed API responses."""
    response = {
        "success": False,
        "error_code": code,
        "message": message
    }
    if details is not None:
        response["details"] = details
        
    return response