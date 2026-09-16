-- Payment-provider registry is backend-owned configuration.
-- Frontend/anon/authenticated clients must not read or mutate provider metadata directly.
-- Backend repositories use the privileged service_role client for these tables.

ALTER TABLE public.payment_provider_plugins ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.payment_provider_methods ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "payment_provider_plugins_no_direct_client_access" ON public.payment_provider_plugins;
CREATE POLICY "payment_provider_plugins_no_direct_client_access"
ON public.payment_provider_plugins
AS RESTRICTIVE
FOR ALL
TO anon, authenticated
USING (false)
WITH CHECK (false);

DROP POLICY IF EXISTS "payment_provider_methods_no_direct_client_access" ON public.payment_provider_methods;
CREATE POLICY "payment_provider_methods_no_direct_client_access"
ON public.payment_provider_methods
AS RESTRICTIVE
FOR ALL
TO anon, authenticated
USING (false)
WITH CHECK (false);
