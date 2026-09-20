begin;

-- Shiprocket is the sole checkout shipping source of truth.
-- Remove legacy global flat/free-shipping settings so they cannot be read
-- by an old code path or reappear as a customer-facing checkout charge.
delete from public.system_settings
where key in ('shipping_enabled', 'flat_shipping_rate', 'free_shipping_threshold');

-- HSN 3917 (plastic tubes, pipes, hoses and fittings) is 18% GST under
-- the current CBIC goods-and-services rate schedule. Correct stale product
-- master data so future checkout/order snapshots use the statutory rate.
update public.products
set gst_percentage = 18
where regexp_replace(coalesce(hsn_code, ''), '[^0-9]', '', 'g') like '3917%';

commit;
