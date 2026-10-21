-- Keep the primary product title aligned with the highest-intent product phrase.
UPDATE public.product_seo
SET
  title = '4.5-Inch Square Kitchen Sink Waste Coupling | Luviio',
  updated_at = now()
WHERE product_id = '27d1e69b-9e1d-416c-8a26-4ed1f3c60110'::uuid;
