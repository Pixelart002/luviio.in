-- Browser clients must not mutate persistence tables directly.
-- FastAPI/service-role is the sole mutation boundary for identity, address,
-- cart and order state. RLS remains defense-in-depth for reads.

REVOKE ALL ON TABLE public.users FROM anon, authenticated;
REVOKE ALL ON TABLE public.addresses FROM anon, authenticated;
REVOKE ALL ON TABLE public.carts FROM anon, authenticated;
REVOKE ALL ON TABLE public.cart_items FROM anon, authenticated;
REVOKE ALL ON TABLE public.orders FROM anon, authenticated;

-- Transactional outbox helpers are trigger-only infrastructure.
REVOKE EXECUTE ON FUNCTION public.enqueue_transactional_inventory_event() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.enqueue_transactional_order_event() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.enqueue_transactional_setting_event() FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.enqueue_transactional_inventory_event() TO service_role;
GRANT EXECUTE ON FUNCTION public.enqueue_transactional_order_event() TO service_role;
GRANT EXECUTE ON FUNCTION public.enqueue_transactional_setting_event() TO service_role;

-- Missing FK indexes identified by the Supabase performance advisor.
CREATE INDEX IF NOT EXISTS idx_addresses_user_id ON public.addresses(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_actor_user_id ON public.audit_logs(actor_user_id);
CREATE INDEX IF NOT EXISTS idx_notification_dlq_user_id ON public.notification_dlq(user_id);
CREATE INDEX IF NOT EXISTS idx_payment_ledger_payment_id ON public.payment_ledger(payment_id);
CREATE INDEX IF NOT EXISTS idx_product_reviews_user_id ON public.product_reviews(user_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_plan_id ON public.user_subscriptions(plan_id);
