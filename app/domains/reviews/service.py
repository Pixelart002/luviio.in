"""Product review business rules."""
from fastapi import HTTPException, status

from app.core.supabase import get_async_admin_supabase
from app.domains.reviews.repository import AsyncReviewRepository


class ReviewService:
    def __init__(self) -> None:
        self.repo = AsyncReviewRepository()

    async def list_approved(self, product_id: str) -> list[dict]:
        sb = await get_async_admin_supabase()
        product = await sb.table("products").select("id,is_active").eq("id", product_id).limit(1).execute()
        if not (getattr(product, "data", None) or []):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
        return await self.repo.list_approved(product_id)

    async def create(self, product_id: str, user_id: str, data: dict) -> dict:
        sb = await get_async_admin_supabase()
        product = await sb.table("products").select("id,is_active").eq("id", product_id).limit(1).execute()
        if not (getattr(product, "data", None) or []):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
        existing = await self.repo.get_user_review(product_id, user_id)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You have already reviewed this product.")

        delivered = await sb.table("orders").select("id").eq("customer_id", user_id).eq("status", "delivered").limit(100).execute()
        order_ids = [row.get("id") for row in (getattr(delivered, "data", None) or []) if row.get("id")]
        if not order_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A delivered purchase is required before reviewing this product.")
        item = await sb.table("order_items").select("id").in_("order_id", order_ids).eq("product_id", product_id).limit(1).execute()
        if not (getattr(item, "data", None) or []):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only customers who purchased this product can review it.")

        try:
            return await self.repo.insert(product_id, user_id, {**data, "status": "pending"})
        except Exception as exc:
            if "product_reviews_product_id_user_id_key" in str(exc):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You have already reviewed this product.") from exc
            raise

    async def list_admin(self, status_filter: str | None = None) -> list[dict]:
        return await self.repo.list_for_admin(status_filter)

    async def moderate(self, review_id: str, status_value: str) -> dict:
        result = await self.repo.update_status(review_id, status_value)
        if not result:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")
        return result
