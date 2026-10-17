-- Harden the default customer-membership trigger against search_path shadowing.
ALTER FUNCTION public.provision_default_free_subscription() SET search_path = '';
