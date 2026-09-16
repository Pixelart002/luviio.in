# Payment GST Insert Invariant

The order insert path uses `jsonb_populate_record()`, which can supply NULL for omitted JSON fields. The `orders` table GST split columns are NOT NULL, so the order GST trigger derives the split from `tax_amount` before insert.

Invariant:

`cgst_amount + sgst_amount + igst_amount = tax_amount`

For `CGST+SGST`, CGST is rounded to two decimals and SGST receives the remainder so the split remains exact. For `IGST`, the full tax amount is assigned to IGST.
