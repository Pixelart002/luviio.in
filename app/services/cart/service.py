"""
Cart Service — Enterprise Business Logic (With Item-Level GST & HSN Support)
============================================================================
Path: app/services/cart/service.py

Compatibility implementation retained while the Cart domain migration is
completed. Pricing ownership is canonicalized under app.domains.pricing.
"""
import asyncio
import logging
import datetime
from decimal import Decimal
from typing import Any, Dict
from fastapi import HTTPException, status

from app.repositories.cart_repo import AsyncCartRepository
from app.domains.pricing.service import get_pricing_from_config
from app.permissions.policies.cart_policies import CartPolicy
from app.constants.cart_messages import CartSecurityMessages, CartMessages
from app.integrations.push.webpush_impl import send_push_to_user
from app.integrations.email.registry import get_email_provider

logger = logging.getLogger(__name__)

class CartService:
    def __init__(self):
        self.repo = AsyncCartRepository()

    async def _calculate_cart_pricing(self, cart_id: str) -> Dict[str, Any]:
        """Calculates cart totals using the PricingEngine SSOT with item-level GST."""
        config, raw_items = await asyncio.gather(
            self.repo.get_pricing_config(),
            self.repo.get_cart_items_with_products(cart_id),
        )
        pricing_engine = get_pricing_from_config(config)

        if not raw_items:
            return {
                "items": [],
                "item_count": 0,
                "subtotal": 0.0,
                "shipping_cost": 0.0,
                "tax_amount": 0.0,
                "total_amount": 0.0,
                "free_shipping_eligible": False,
                "amount_to_free_shipping": float(pricing_engine.shipping_threshold) if pricing_engine.shipping_enabled else 0.0,
                "free_shipping_threshold": float(pricing_engine.shipping_threshold) if pricing_engine.shipping_enabled else 0.0,
                "has_unavailable_items": False,
                "currency": "INR",
            }

        enriched = []
        subtotal = Decimal("0")
        has_unavailable = False

        for row in raw_items:
            prod = row.get("products") or {}
            qty = row["quantity"]
            snapshot = Decimal(str(row["price_snapshot"]))
            current_price = Decimal(str(prod.get("price", snapshot)))
            comp_p = prod.get("compare_price")
            compare_price = float(comp_p) if comp_p is not None else 0.0
            line_total = current_price * qty
            subtotal += line_total
            in_stock = prod.get("is_active", True) and prod.get("stock", 0) >= qty
            price_changed = abs(float(current_price) - float(snapshot)) > 0.001

            if not in_stock:
                has_unavailable = True

            hsn_code = str(prod.get("hsn_code") or row.get("hsn_code") or "9988").strip()
            gst_percentage = int(prod.get("gst_percentage") if prod.get("gst_percentage") is not None else (row.get("gst_percentage") if row.get("gst_percentage") is not None else 18))

            enriched.append({
                "id": str(row["id"]),
                "product_id": str(row["product_id"]),
                "name": str(prod.get("name", "")),
                "slug": str(prod.get("slug", "")),
                "image_url": prod.get("image_url"),
                "hsn_code": hsn_code,
                "gst_percentage": gst_percentage,
                "quantity": qty,
                "unit_price": float(current_price),
                "compare_price": compare_price,
                "price_snapshot": float(snapshot),
                "line_total": float(line_total),
                "stock": int(prod.get("stock", 0)),
                "in_stock": in_stock,
                "is_active": prod.get("is_active", True),
                "price_changed": price_changed,
                "added_at": str(row["added_at"]),
            })

        breakdown = pricing_engine.calculate(items=enriched)
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
            "has_unavailable_items": has_unavailable,
            "currency": "INR"
        }

    async def get_cart(self, user_id: str) -> Dict[str, Any]:
        cart = await self.repo.get_or_create_cart(user_id)
        return await self._calculate_cart_pricing(cart["id"])

    async def add_item(self, user_id: str, product_id: str, quantity: int) -> Dict[str, Any]:
        prod = await self.repo.get_product_stock_status(product_id)
        CartPolicy.assert_product_available(prod, quantity)
        cart = await self.repo.get_or_create_cart(user_id)
        existing = await self.repo.get_cart_item(cart["id"], product_id)
        if existing:
            new_qty = existing["quantity"] + quantity
            CartPolicy.assert_item_limit(new_qty)
            CartPolicy.assert_product_available(prod, new_qty)
            await self.repo.update_item_quantity(existing["id"], new_qty)
        else:
            CartPolicy.assert_item_limit(quantity)
            await self.repo.add_item_to_cart(cart["id"], product_id, quantity, float(prod["price"]))
        return await self._calculate_cart_pricing(cart["id"])

    async def update_item(self, user_id: str, product_id: str, quantity: int) -> Dict[str, Any]:
        CartPolicy.assert_item_limit(quantity)
        cart = await self.repo.get_or_create_cart(user_id)
        prod = await self.repo.get_product_stock_status(product_id)
        CartPolicy.assert_product_available(prod, quantity)
        success = await self.repo.update_item_quantity_by_product(cart["id"], product_id, quantity)
        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=CartSecurityMessages.ITEM_NOT_FOUND)
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
        CartPolicy.assert_can_remind(cart)
        items = cart.get("cart_items") or []
        user_info = cart.get("users") or {}
        user_id = cart["user_id"]
        email, name = user_info.get("email", ""), user_info.get("full_name", "there")
        push_sent, email_sent = 0, False
        try:
            from app.core.supabase import get_admin_supabase
            push_sent = send_push_to_user(
                get_admin_supabase(), user_id,
                title="🛒 Left something behind?",
                body=f"Your cart has {len(items)} item(s) waiting.",
                icon="/icons/cart.png", url="/cart.html"
            )
        except Exception as exc:
            logger.warning("WebPush failed for cart %s: %s", cart_id, exc)
        if email:
            try:
                get_email_provider("resend").send_cart_reminder_email(email, name, items)
                email_sent = True
            except Exception as exc:
                logger.warning("Email reminder failed for cart %s: %s", cart_id, exc)
        return {"message": CartMessages.REMINDER_SENT, "push_sent": str(push_sent > 0), "email_sent": str(email_sent)}
