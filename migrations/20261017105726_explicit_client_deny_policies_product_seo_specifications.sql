-- Product SEO and normalized specifications are accessed through the trusted
-- server-side Supabase admin client in app/domains/products/repository.py.
-- Keep direct anon/authenticated Data API access explicitly denied.
DO $migration$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname='public' AND tablename='product_seo'
      AND policyname='deny_client_access_product_seo'
  ) THEN
    CREATE POLICY deny_client_access_product_seo
      ON public.product_seo
      FOR ALL TO anon, authenticated
      USING (false)
      WITH CHECK (false);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname='public' AND tablename='product_specifications'
      AND policyname='deny_client_access_product_specifications'
  ) THEN
    CREATE POLICY deny_client_access_product_specifications
      ON public.product_specifications
      FOR ALL TO anon, authenticated
      USING (false)
      WITH CHECK (false);
  END IF;
END
$migration$;

COMMENT ON TABLE public.product_seo IS
  'Backend-managed product SEO metadata. Client roles anon/authenticated are explicitly denied by RLS; application backend uses the privileged server-side Supabase client.';

COMMENT ON TABLE public.product_specifications IS
  'Backend-managed normalized product specifications. Client roles anon/authenticated are explicitly denied by RLS; application backend uses the privileged server-side Supabase client.';
