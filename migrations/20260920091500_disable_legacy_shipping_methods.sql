begin;

-- Checkout no longer consumes the legacy shipping_methods calculator.
-- Keep the rows for historical/admin visibility, but prevent them from being
-- offered as active customer shipping methods.
update public.shipping_methods
set is_active = false
where is_active = true;

commit;
