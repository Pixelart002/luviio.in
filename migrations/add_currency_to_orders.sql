-- Migration: Add currency column to orders table
-- Fixes: HTTPException "Order creation failed (Database Error)" caused by
--        PostgREST rejecting inserts with a 'currency' field not in the schema.

ALTER TABLE public.orders
  ADD COLUMN IF NOT EXISTS currency text DEFAULT 'INR';

-- Reload PostgREST schema cache so the new column is immediately visible
-- without requiring a service restart.
SELECT pg_notify('pgrst', 'reload schema');