-- LUVIIO security + performance hardening
-- Run once in Supabase SQL Editor.
-- This migration is intentionally fail-closed and idempotent.

-- 1) Remove redundant UNIQUE indexes on orders.
-- Keep the canonical idx_orders_idem definition.
DROP INDEX IF EXISTS public.orders_idempotency_key_idx;
DROP INDEX IF EXISTS public.uq_orders_user_idempotency;

-- 2) Speed up the hottest checkout guard without indexing cancelled/paid rows.
CREATE INDEX IF NOT EXISTS idx_orders_customer_pending
    ON public.orders (customer_id, created_at DESC)
    WHERE status = 'pending';

-- 3) SECURITY DEFINER functions must not be callable by public API roles.
-- Backend uses the Supabase service-role client for these operations.
REVOKE EXECUTE ON FUNCTION public.consume_coupon(uuid, uuid, uuid)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.cancel_order_and_release_stock(uuid, text)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.claim_webhook_event(text, text, text)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.create_pending_order_with_reservation(jsonb, jsonb)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.mark_payment_failed(uuid, uuid, text, numeric, text, text)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.mark_webhook_event_processed(text)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.record_payment_attempt(uuid, uuid, text, numeric, text, text, text, text, text, text)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.rpc_admin_update_order_status(uuid, text, text, text)
    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.settle_order_transaction(uuid, text, numeric, uuid, text)
    FROM PUBLIC, anon, authenticated;

-- Explicitly grant backend role access after revocation.
GRANT EXECUTE ON FUNCTION public.consume_coupon(uuid, uuid, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.cancel_order_and_release_stock(uuid, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_webhook_event(text, text, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.create_pending_order_with_reservation(jsonb, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.mark_payment_failed(uuid, uuid, text, numeric, text, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.mark_webhook_event_processed(text) TO service_role;
GRANT EXECUTE ON FUNCTION public.record_payment_attempt(uuid, uuid, text, numeric, text, text, text, text, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.rpc_admin_update_order_status(uuid, text, text, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.settle_order_transaction(uuid, text, numeric, uuid, text) TO service_role;

-- 4) Harden SECURITY DEFINER search paths against search_path hijacking.
ALTER FUNCTION public.consume_coupon(uuid, uuid, uuid)
    SET search_path = public, pg_temp;
ALTER FUNCTION public.cancel_order_and_release_stock(uuid, text)
    SET search_path = public, pg_temp;
ALTER FUNCTION public.claim_webhook_event(text, text, text)
    SET search_path = public, pg_temp;
ALTER FUNCTION public.create_pending_order_with_reservation(jsonb, jsonb)
    SET search_path = public, pg_temp;
ALTER FUNCTION public.mark_payment_failed(uuid, uuid, text, numeric, text, text)
    SET search_path = public, pg_temp;
ALTER FUNCTION public.mark_webhook_event_processed(text)
    SET search_path = public, pg_temp;
ALTER FUNCTION public.record_payment_attempt(uuid, uuid, text, numeric, text, text, text, text, text, text)
    SET search_path = public, pg_temp;
ALTER FUNCTION public.rpc_admin_update_order_status(uuid, text, text, text)
    SET search_path = public, pg_temp;
ALTER FUNCTION public.settle_order_transaction(uuid, text, numeric, uuid, text)
    SET search_path = public, pg_temp;

-- 5) Backend-only data model: prevent direct PostgREST writes from client roles.
-- Catalogue remains readable through the application API; all mutations go through
-- FastAPI so validation, RBAC, audit and transactional invariants cannot be bypassed.
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON public.users, public.addresses, public.carts, public.cart_items,
       public.orders, public.order_items, public.pricing_config,
       public.payment_attempts, public.payments, public.stock_audit,
       public.coupons, public.coupon_redemptions, public.shipping_methods,
       public.role_permissions, public.user_action_controls,
       public.user_subscriptions, public.subscription_plans
    FROM anon, authenticated;

-- Keep direct public catalogue reads explicitly available where already intended.
GRANT SELECT ON public.products, public.categories, public.product_images
    TO anon, authenticated;
