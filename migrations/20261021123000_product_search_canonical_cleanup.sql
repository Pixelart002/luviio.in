-- Align indexed product metadata with the preferred www canonical host.
-- Keep product and order records intact; only search directives and SEO copy change.
INSERT INTO public.product_seo (
  product_id,
  title,
  description,
  canonical_url,
  robots_index,
  robots_follow,
  updated_at
)
VALUES
  (
    '27d1e69b-9e1d-416c-8a26-4ed1f3c60110'::uuid,
    '4.5-Inch Square Stainless Steel Sink Coupling | Luviio',
    'Buy a 4.5-inch square stainless-steel kitchen sink waste coupling with a removable grid basket, durable PVC body and threaded adapters.',
    NULL,
    true,
    true,
    now()
  ),
  (
    '8182d366-7151-48ae-ac48-df083495f899'::uuid,
    'Plated Square Drainer | Luviio',
    'Plated square steel drainer. Confirm the drain opening size and fitting compatibility before purchase.',
    NULL,
    false,
    true,
    now()
  ),
  (
    '551e931a-6f0f-45a4-90af-1765d516e269'::uuid,
    NULL,
    NULL,
    NULL,
    false,
    true,
    now()
  ),
  (
    '5dc8bf17-190c-4289-9f7d-f475303b7e13'::uuid,
    NULL,
    NULL,
    NULL,
    false,
    true,
    now()
  )
ON CONFLICT (product_id) DO UPDATE SET
  title = EXCLUDED.title,
  description = EXCLUDED.description,
  canonical_url = EXCLUDED.canonical_url,
  robots_index = EXCLUDED.robots_index,
  robots_follow = EXCLUDED.robots_follow,
  updated_at = now();
