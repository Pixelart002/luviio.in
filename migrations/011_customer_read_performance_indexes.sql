-- Customer-facing read-path indexes.
-- These support the hot paths observed in production logs:
--   GET /api/v1/orders/my ... ORDER BY created_at DESC
--   GET /api/v1/cart ... cart_items by cart_id
-- Keep these additive; no pricing, payment, auth, or business rules are changed.

CREATE INDEX IF NOT EXISTS orders_customer_created_at_idx
    ON public.orders (customer_id, created_at DESC);

CREATE INDEX IF NOT EXISTS cart_items_cart_id_added_at_idx
    ON public.cart_items (cart_id, added_at ASC);
