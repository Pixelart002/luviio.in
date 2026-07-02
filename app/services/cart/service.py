import asyncio
import logging
import datetime
from decimal import Decimal
from typing import Any, Dict

from app.repositories.cart_repo import AsyncCartRepository
from app.services.pricing import get_pricing_from_config
from app.integrations.push.webpush_impl import send_push_to_user
from app.integrations.email.registry import get_email_provider
from app.core.exceptions import ProductNotFound, OutOfStockException, LuviioException

logger = logging.getLogger(__name__)

class CartService:
    def __init__(self):
        self.repo = AsyncCartRepository()

    async def _calculate_cart_pricing(self, cart_id: str) -> Dict[str, Any]:
        """Calculates cart totals using the PricingEngine SSOT."""
        config, raw_items = await asyncio.gather(
            self.repo.get_pricing_config(),
            self.repo.get_cart_items_with_products(cart_id),
        )
        pricing_engine = get_pricing_from_config(config)

        enriched = []
        subtotal = Decimal("0")
        has_unavailable = False

        for row in raw_items:
            prod = row.get("products") or {}
            qty = row["quantity"]
            snapshot = Decimal(str(row["price_snapshot"]))
            current_price = Decimal(str(prod.get("price", snapshot)))
            line_total = current_price * qty
            subtotal += line_total

            in_stock = prod.get("is_active", True) and prod.get("stock", 0) >= qty
            price_changed = abs(float(current_price) - float(snapshot)) > 0.001

            if not in_stock: has_unavailable = True

            enriched.append({
                "id": row["id"],
                "product_id": row["product_id"],
                "name": prod.get("name", ""),
                "slug": prod.get("slug", ""),
                "image_url": prod.get("image_url"),
                "quantity": qty,
                "unit_price": float(current_price),
                "price_snapshot": float(snapshot),
                "line_total": float(line_total),
                "stock": prod.get("stock", 0),
                "in_stock": in_stock,
                "is_active": prod.get("is_active", True),
                "price_changed": price_changed,
                "added_at": row["added_at"],
            })

        breakdown = pricing_engine.calculate(subtotal)
        pricing_dict = breakdown.as_dict()

        amount_to_free = 0.0
        if pricing_engine.shipping_enabled and subtotal < pricing_engine.shipping_threshold:
            amount_to_free = round(max(0.0, float(pricing_engine.shipping_threshold) - float(subtotal)), 2)

        return {
            "items": enriched,
            "item_count": len(enriched),
            **pricing_dict,
            "free_shipping_eligible": breakdown.shipping == Decimal("0") and subtotal > Decimal("0"),
            "amount_to_free_shipping": amount_to_free,
            "free_shipping_threshold": float(pricing_engine.shipping_threshold),
            "tax_rate_pct": float(pricing_engine.tax_rate * 100),
            "has_unavailable_items": has_unavailable,
        }

    async def get_cart(self, user_id: str) -> Dict[str, Any]:
        cart = await self.repo.get_or_create_cart(user_id)
        return await self._calculate_cart_pricing(cart["id"])

    async def add_item(self, user_id: str, product_id: str, quantity: int) -> Dict[str, Any]:
        prod = await self.repo.get_product_stock_status(product_id)
        if not prod or not prod.get("is_active"):
            raise ProductNotFound(product_id)
        if prod["stock"] < quantity:
            raise OutOfStockException(f"Only {prod['stock']} units available")

        cart = await self.repo.get_or_create_cart(user_id)
        existing = await self.repo.get_cart_item(cart["id"], product_id)

        if existing:
            new_qty = existing["quantity"] + quantity
            if new_qty > 100:
                raise LuviioException("Maximum 100 units per item", "LIMIT_EXCEEDED", 400)
            if prod["stock"] < new_qty:
                raise OutOfStockException(f"Only {prod['stock']} units available")
            await self.repo.update_item_quantity(existing["id"], new_qty)
        else:
            await self.repo.add_item_to_cart(cart["id"], product_id, quantity, float(prod["price"]))

        return await self._calculate_cart_pricing(cart["id"])

    async def update_item(self, user_id: str, product_id: str, quantity: int) -> Dict[str, Any]:
        cart = await self.repo.get_or_create_cart(user_id)
        prod = await self.repo.get_product_stock_status(product_id)

        if not prod or not prod.get("is_active"):
            raise ProductNotFound(product_id)
        if prod["stock"] < quantity:
            raise OutOfStockException(f"Only {prod['stock']} units available")

        success = await self.repo.update_item_quantity_by_product(cart["id"], product_id, quantity)
        if not success:
            raise LuviioException("Item not in cart", "NOT_FOUND", 404)

        return await self._calculate_cart_pricing(cart["id"])

    async def remove_item(self, user_id: str, product_id: str) -> Dict[str, Any]:
        cart = await self.repo.get_or_create_cart(user_id)
        await self.repo.remove_item(cart["id"], product_id)
        return await self._calculate_cart_pricing(cart["id"])

    async def clear_cart(self, user_id: str) -> None:
        cart = await self.repo.get_or_create_cart(user_id)
        await self.repo.clear_cart(cart["id"])

    async def get_abandoned_carts(self, hours: int, page: int, page_size: int) -> Dict[str, Any]:
        offset = (page - 1) * page_size
        cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)).isoformat()
        
        rows, total = await self.repo.get_abandoned_carts(cutoff, offset, page_size)
        for row in rows:
            items = row.get("cart_items", [])
            row["item_count"] = len(items)
            row["estimated_value"] = float(sum(Decimal(str(i["price_snapshot"])) * i["quantity"] for i in items))

        return {
            "items": rows, "total": total, "page": page, "page_size": page_size,
            "pages": -(-total // page_size) if page_size > 0 else 0, "hours_threshold": hours
        }

    async def send_cart_reminder(self, cart_id: str) -> Dict[str, str]:
        cart = await self.repo.get_cart_for_reminder(cart_id)
        if not cart: raise LuviioException("Cart not found", "NOT_FOUND", 404)
        
        items = cart.get("cart_items") or []
        if not items: raise LuviioException("Cart is empty — no reminder needed", "EMPTY_CART", 400)

        user_info = cart.get("users") or {}
        user_id = cart["user_id"]
        email, name = user_info.get("email", ""), user_info.get("full_name", "there")

        push_sent, email_sent = 0, False
        try:
            from app.core.supabase import get_admin_supabase
            push_sent = send_push_to_user(get_admin_supabase(), user_id, title="🛒 Left something behind?", body=f"Your cart has {len(items)} item(s) waiting.", icon="/icons/cart.png", url="/cart.html")
        except Exception: pass

        if email:
            try:
                get_email_provider("resend").send_cart_reminder_email(email, name, items)
                email_sent = True
            except Exception: pass

        return {"message": "Reminder sent", "push_sent": str(push_sent > 0), "email_sent": str(email_sent)}