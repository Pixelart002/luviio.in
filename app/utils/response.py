from typing import Any, Generic, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar('T')

class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_previous: bool

class APIResponse(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    error_code: Optional[str] = None
    message: Optional[str] = None
    meta: Optional[PaginationMeta] = None

def success_response(data: Any = None, message: str = "Success", meta: Optional[PaginationMeta] = None) -> dict:
    """
    Standard wrapper for all successful API responses.
    """
    response = APIResponse(success=True, data=data, message=message, meta=meta)
    return response.model_dump(exclude_none=True)

def error_response(code: str, message: str, details: Any = None) -> dict:
    """
    Standard wrapper for all failed API responses.
    """
    return {
        "success": False,
        "error_code": code,
        "message": message,
        "details": details
    }