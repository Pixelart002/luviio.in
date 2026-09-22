-- Security hardening: prevent untrusted clients from creating objects in public
-- and from directly mutating server-managed commerce/account records.

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO anon, authenticated;

-- All public RPCs are backend/service-role implementation details. Trigger
-- functions do not need client EXECUTE privileges; service_role keeps access.
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO service_role;

-- User profile writes go through the backend repository, which applies the
-- domain-level field/role controls. Direct client UPDATE would otherwise allow
-- sensitive columns such as role/is_active to be changed through RLS.
REVOKE INSERT, UPDATE, DELETE ON TABLE public.users FROM anon, authenticated;
DROP POLICY IF EXISTS users_update_own ON public.users;

-- Orders are server-managed: checkout, payment, cancellation and status changes
-- must go through domain services/RPCs, not direct PostgREST table mutations.
REVOKE INSERT, UPDATE, DELETE ON TABLE public.orders FROM anon, authenticated;
DROP POLICY IF EXISTS orders_insert_own ON public.orders;
DROP POLICY IF EXISTS orders_update_own ON public.orders;

-- Defense-in-depth: explicitly deny client mutations on other server-managed
-- commerce/audit tables even if a table grant is accidentally reintroduced.
DO $$
DECLARE
  t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'audit_logs', 'auth_throttle_state', 'checkout_payment_attempts',
    'coupon_redemptions', 'coupons', 'event_outbox', 'inventory_activity',
    'invoice_items', 'invoices', 'notification_dlq', 'order_items',
    'payment_attempts', 'payment_ledger', 'payment_provider_methods',
    'payment_provider_plugins', 'payment_retry_policy',
    'payment_retry_reservations', 'payments', 'product_reviews',
    'push_subscriptions', 'role_permissions', 'settings_audit_log',
    'shipping_methods', 'stock_audit', 'system_settings',
    'user_action_controls', 'user_subscriptions', 'webhook_events_ledger'
  ]
  LOOP
    EXECUTE format('REVOKE INSERT, UPDATE, DELETE ON TABLE public.%I FROM anon, authenticated', t);
  END LOOP;
END $$;

-- Remove pg_temp from SECURITY DEFINER search paths. public is now non-CREATE
-- for untrusted roles, so object shadowing through temporary schemas is closed.
ALTER FUNCTION public.activate_shipping_method(uuid) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.admin_adjust_stock(uuid, integer, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.admin_payment_telemetry(integer, integer) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.auth_throttle_check(text, text, integer, integer) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.auth_throttle_record_failure(text, text, integer, integer, integer) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.auth_throttle_reset(text, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.cancel_order_and_release_stock(uuid, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.claim_event_outbox(integer) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.claim_webhook_event(text, text, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.claim_webhook_event_provider(text, text, text, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.cleanup_expired_coupon_reservations() SET search_path TO pg_catalog, public;
ALTER FUNCTION public.create_checkout_payment_attempt(uuid, uuid, text, bigint, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.create_pending_order_with_payment(jsonb, jsonb, text, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.create_pending_order_with_reservation(jsonb, jsonb) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.enqueue_transactional_inventory_event() SET search_path TO pg_catalog, public;
ALTER FUNCTION public.enqueue_transactional_order_event() SET search_path TO pg_catalog, public;
ALTER FUNCTION public.enqueue_transactional_setting_event() SET search_path TO pg_catalog, public;
ALTER FUNCTION public.inventory_apply_delta(uuid, integer, text, text, text, uuid, jsonb) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.inventory_receive_stock(uuid, integer, text, uuid, jsonb) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.inventory_reconcile_stock(uuid, integer, text, jsonb) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.inventory_record_damage(uuid, integer, text, uuid, jsonb) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.inventory_record_return(uuid, integer, text, uuid, jsonb) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.inventory_record_wastage(uuid, integer, text, uuid, jsonb) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.mark_payment_failed(uuid, uuid, text, numeric, text, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.mark_webhook_event_processed(text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.record_coupon_redemption(uuid, uuid, uuid, numeric) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.record_payment_attempt(uuid, uuid, text, numeric, text, text, text, text, text, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.record_payment_attempt_provider(uuid, uuid, text, text, numeric, text, text, text, text, text, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.release_coupon_reservation(uuid) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.release_expired_coupon_reservations() SET search_path TO pg_catalog, public;
ALTER FUNCTION public.release_payment_retry(uuid) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.reserve_coupon_for_order(uuid, uuid, uuid, numeric) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.reserve_payment_retry(uuid, uuid, text, integer, integer) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.reserve_payment_retry_provider(uuid, uuid, text, text, integer, integer) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.rpc_admin_update_order_status(uuid, text, text, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.settle_order_transaction(uuid, text, numeric, uuid, text, text, text, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.settle_payment_transaction(uuid, text, text, numeric, uuid, text, text) SET search_path TO pg_catalog, public;
ALTER FUNCTION public.sync_cod_payment_header() SET search_path TO pg_catalog, public;
ALTER FUNCTION public.sync_cod_payment_state() SET search_path TO pg_catalog, public;
ALTER FUNCTION public.sync_retry_reservation_to_payment() SET search_path TO pg_catalog, public;
ALTER FUNCTION public.update_checkout_payment_attempt(uuid, text, text, text) SET search_path TO pg_catalog, public;
