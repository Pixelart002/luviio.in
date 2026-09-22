-- Roll back the optional mid-order payment-method change feature.
-- The existing global payment-attempt limit and normal retry flow remain intact.
DROP FUNCTION IF EXISTS public.assert_payment_method_change_allowed(uuid, uuid, text, integer);
DROP FUNCTION IF EXISTS public.change_payment_method_after_limit(uuid, uuid, text, text, text, uuid, integer);
DROP FUNCTION IF EXISTS public.reserve_payment_method_change(uuid, uuid, text, integer);
