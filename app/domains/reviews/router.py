"""Product review HTTP boundary."""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.dependencies import get_user_id_strict, require_permission
from app.domains.reviews.schemas import ReviewCreate, ReviewModerationUpdate
from app.domains.reviews.service import ReviewService
from app.permissions.reviews import ReviewPermissions
from app.utils.response import success_response

router = APIRouter(prefix="/reviews", tags=["Reviews"])
limiter = Limiter(key_func=get_remote_address)


@router.get("/products/{product_id}", status_code=status.HTTP_200_OK)
async def list_product_reviews(request: Request, product_id: UUID) -> dict[str, Any]:
    reviews = await ReviewService().list_approved(str(product_id))
    return success_response(data=reviews)


@router.post("/products/{product_id}", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_product_review(request: Request, product_id: UUID, payload: ReviewCreate, user_id: str = Depends(get_user_id_strict)) -> dict[str, Any]:
    result = await ReviewService().create(str(product_id), user_id, payload.model_dump())
    return success_response(data=result, message="Review submitted for moderation.")


@router.get("/me", status_code=status.HTTP_200_OK)
async def my_reviews(request: Request, user_id: str = Depends(get_user_id_strict)) -> dict[str, Any]:
    # This endpoint is intentionally omitted from the public surface until a dedicated
    # user-review repository projection is needed; return only the authenticated user's rows.
    from app.core.supabase import get_async_admin_supabase
    sb = await get_async_admin_supabase()
    result = await sb.table("product_reviews").select("id,product_id,rating,title,body,status,created_at,updated_at").eq("user_id", user_id).order("created_at", desc=True).limit(100).execute()
    return success_response(data=getattr(result, "data", None) or [])


@router.get("/admin", dependencies=[Depends(require_permission(ReviewPermissions.MODERATE))], status_code=status.HTTP_200_OK)
async def admin_reviews(request: Request, status_filter: str | None = Query(None, pattern=r"^(pending|approved|rejected)$")) -> dict[str, Any]:
    return success_response(data=await ReviewService().list_admin(status_filter))


@router.patch("/admin/{review_id}", dependencies=[Depends(require_permission(ReviewPermissions.MODERATE))], status_code=status.HTTP_200_OK)
async def moderate_review(request: Request, review_id: UUID, payload: ReviewModerationUpdate) -> dict[str, Any]:
    return success_response(data=await ReviewService().moderate(str(review_id), payload.status), message="Review status updated.")
