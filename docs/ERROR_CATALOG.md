# Error Catalog

## Payment intent / order reservation

When `POST /api/v1/payments/create-intent` creates a provider payment intent successfully but the atomic order reservation fails, the API returns a conflict response and the order is not created.

A known failure mode was an omitted GST split in `p_order_data`. The database trigger now derives `cgst_amount`, `sgst_amount`, and `igst_amount` from `tax_amount` before the `orders` row is inserted, including when the RPC uses `jsonb_populate_record()`.

Expected invariant:

`cgst_amount + sgst_amount + igst_amount = tax_amount`

The Stripe provider response itself is independent of this database validation step.
