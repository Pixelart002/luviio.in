"""Async persistence for product reviews."""
from typing import Any

from app.core.supabase import get_async_admin_supabase


class AsyncReviewRepository:
    async def list_approved(self, product_id: str) -> list[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        res = await (
            sb.table("product_reviews")
            .select("id, product_id, user_id, rating, title, body, created_at, users(full_name)")
            .eq("product_id", product_id)
            .eq("status", "approved")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        return [self._public(row) for row in rows]

    async def get_user_review(self, product_id: str, user_id: str) -> dict[str, Any] | None:
        sb = await get_async_admin_supabase()
        res = await (
            sb.table("product_reviews")
            .select("id, product_id, user_id, rating, title, body, status, created_at, updated_at")
            .eq("product_id", product_id)
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = getattr(res, "data", None) or []
        return rows[0] if rows else None

    async def insert(self, product_id: str, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        sb = await get_async_admin_supabase()
        res = await sb.table("product_reviews").insert({"product_id": product_id, "user_id": user_id, **data}).execute()
        rows = getattr(res, "data", None) or []
        return rows[0] if rows else {}

    async def list_for_admin(self, status_filter: str | None = None) -> list[dict[str, Any]]:
        sb = await get_async_admin_supabase()
        query = sb.table("product_reviews").select("id, product_id, user_id, rating, title, body, status, created_at, updated_at, products(name,slug), users(full_name)").order("created_at", desc=True).limit(200)
        if status_filter:
            query = query.eq("status", status_filter)
        res = await query.execute()
        return getattr(res, "data", None) or []

    async def update_status(self, review_id: str, status_value: str) -> dict[str, Any]:
        sb = await get_async_admin_supabase()
        res = await sb.table("product_reviews").update({"status": status_value, "updated_at": "now()"}).eq("id", review_id).execute()
        rows = getattr(res, "data", None) or []
        return rows[0] if rows else {}

    @staticmethod
    def _public(row: dict[str, Any]) -> dict[str, Any]:
        user = row.get("users") if isinstance(row.get("users"), dict) else {}
        return {
            "id": row.get("id"),
            "product_id": row.get("product_id"),
            "rating": row.get("rating"),
            "title": row.get("title"),
            "body": row.get("body"),
            "created_at": row.get("created_at"),
            "author_name": user.get("full_name") or "Luviio customer",
        }
