-- LUVIIO — cover the composite measurement-unit foreign key.
-- Keeps product measurement joins/index-backed FK checks efficient.

CREATE INDEX IF NOT EXISTS idx_products_measurement_type_unit
ON public.products (measurement_type, measurement_unit);
