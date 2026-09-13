-- Initial PaymentIntent lifecycle states were historically stored as attempt rows.
-- They are not real payment attempts. Remove those phantom rows and rebuild
-- aggregate attempt counters from terminal payment-attempt history.

DELETE FROM public.payment_attempts
WHERE status IN ('requires_payment_method','requires_confirmation','requires_action','processing');

WITH agg AS (
  SELECT
    p.id AS payment_id,
    COALESCE(MAX(a.attempt_number),0) AS max_attempt,
    COALESCE(MAX(a.attempt_number) FILTER (WHERE a.status='succeeded'),0) AS success_attempt,
    COUNT(a.id)::integer AS attempt_count
  FROM public.payments p
  LEFT JOIN public.payment_attempts a ON a.payment_id=p.id
  GROUP BY p.id
)
UPDATE public.payments p
SET attempt_number=g.max_attempt,
    total_attempts=g.attempt_count,
    latest_attempt_number=g.max_attempt,
    successful_attempt_number=NULLIF(g.success_attempt,0),
    latest_payment_intent_id=COALESCE(
      (SELECT a.stripe_payment_intent_id FROM public.payment_attempts a
       WHERE a.payment_id=p.id
       ORDER BY a.attempt_number DESC,a.created_at DESC
       LIMIT 1),
      p.latest_payment_intent_id
    ),
    updated_at=now()
FROM agg g
WHERE p.id=g.payment_id;
