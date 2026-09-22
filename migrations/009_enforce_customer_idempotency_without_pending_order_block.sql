-- Legitimate customers may create multiple pending orders.
-- Duplicate checkout attempts are identified only by the same customer + idempotency key.
-- Existing data was checked for duplicates before applying the production index.
CREATE UNIQUE INDEX IF NOT EXISTS orders_customer_id_idempotency_key_uidx
    ON public.orders (customer_id, idempotency_key)
    WHERE customer_id IS NOT NULL
      AND idempotency_key IS NOT NULL
      AND btrim(idempotency_key) <> '';

COMMENT ON INDEX public.orders_customer_id_idempotency_key_uidx IS
    'Prevents duplicate checkout operations per customer while allowing unlimited independent orders with different idempotency keys.';
