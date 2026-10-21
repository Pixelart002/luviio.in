-- The legacy floor-drainer URL maps to the live "square" catalogue record.
-- Give that real item distinct, relevant metadata before making it indexable.
UPDATE public.product_seo
SET
  title = 'Plated Square Floor Drainer | Luviio',
  description = 'Plated square floor drainer for floor drainage. Check the drain opening size and fitting compatibility before purchase.',
  canonical_url = NULL,
  robots_index = true,
  robots_follow = true,
  updated_at = now()
WHERE product_id = '8182d366-7151-48ae-ac48-df083495f899'::uuid;
