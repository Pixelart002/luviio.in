-- Canonical financial configuration lives in system_settings.
insert into public.system_settings (key, value, category, description, is_public, is_locked)
values (
  'tax_enabled', 'true'::jsonb, 'financial',
  'Enable product-level GST calculation at checkout. GST percentage is sourced from each product.',
  true, true
)
on conflict (key) do update
set value = excluded.value,
    category = excluded.category,
    description = excluded.description,
    is_public = excluded.is_public,
    is_locked = excluded.is_locked;

delete from public.system_settings
where key in ('tax_rate', 'default_tax_rate_percentage');

update public.system_settings
set value = '"🚀 Free Shipping on orders above ₹1499!"'::jsonb
where key = 'announcement_banner';

-- SECURITY DEFINER routines are service-role infrastructure, never browser-callable.
alter function public.set_order_payment_method() set search_path = public, pg_catalog;

revoke execute on function public.release_coupon_reservation(uuid) from public;
revoke execute on function public.release_payment_retry(uuid) from public;
revoke execute on function public.reserve_coupon_for_order(uuid, uuid, uuid, numeric) from public;
revoke execute on function public.settle_order_transaction(uuid, text, numeric, uuid, text, text, text, text) from public;
revoke execute on function public.sync_cod_payment_header() from public;
revoke execute on function public.sync_cod_payment_state() from public;
revoke execute on function public.sync_retry_reservation_to_payment() from public;

grant execute on function public.release_coupon_reservation(uuid) to service_role;
grant execute on function public.release_payment_retry(uuid) to service_role;
grant execute on function public.reserve_coupon_for_order(uuid, uuid, uuid, numeric) to service_role;
grant execute on function public.settle_order_transaction(uuid, text, numeric, uuid, text, text, text, text) to service_role;
grant execute on function public.sync_cod_payment_header() to service_role;
grant execute on function public.sync_cod_payment_state() to service_role;
grant execute on function public.sync_retry_reservation_to_payment() to service_role;
