-- Luviio final RLS/performance cleanup.
-- Reduces redundant PERMISSIVE policies and records the safe FK/ledger indexes
-- applied in production. Service-role clients bypass RLS, so dedicated
-- service-role policies are unnecessary.

DROP POLICY IF EXISTS "cart_items_owner" ON public.cart_items;
DROP POLICY IF EXISTS "Users can manage own cart items" ON public.cart_items;
DROP POLICY IF EXISTS "carts_owner" ON public.carts;
DROP POLICY IF EXISTS "Users can manage own cart" ON public.carts;
DROP POLICY IF EXISTS "service_role_all_addresses" ON public.addresses;
DROP POLICY IF EXISTS "service_role_all_categories" ON public.categories;
DROP POLICY IF EXISTS "service_role_all_images" ON public.product_images;
DROP POLICY IF EXISTS "service_role_all_products" ON public.products;
DROP POLICY IF EXISTS "service_role_all_order_items" ON public.order_items;
DROP POLICY IF EXISTS "service_role_all_orders" ON public.orders;
DROP POLICY IF EXISTS "service_role_all_users" ON public.users;
DROP POLICY IF EXISTS "admin_write_coupons" ON public.coupons;
DROP POLICY IF EXISTS "admin_write_role_permissions" ON public.role_permissions;
DROP POLICY IF EXISTS "admin_write_shipping_methods" ON public.shipping_methods;
DROP POLICY IF EXISTS "admin_write_subscription_plans" ON public.subscription_plans;
DROP POLICY IF EXISTS "admin_write_user_action_controls" ON public.user_action_controls;

CREATE INDEX IF NOT EXISTS idx_cart_items_product_id ON public.cart_items(product_id);
CREATE INDEX IF NOT EXISTS idx_orders_shipping_address_id ON public.orders(shipping_address_id);
CREATE INDEX IF NOT EXISTS idx_product_images_product_id ON public.product_images(product_id);
CREATE INDEX IF NOT EXISTS idx_products_category_id ON public.products(category_id);
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_plan_id ON public.user_subscriptions(plan_id);
CREATE UNIQUE INDEX IF NOT EXISTS webhook_events_ledger_event_id_uidx
    ON public.webhook_events_ledger(event_id);
