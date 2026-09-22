-- Explicit deny policies keep the durable checkout-attempt table service-role-only.
CREATE POLICY checkout_payment_attempts_deny_anon
  ON public.checkout_payment_attempts
  FOR ALL TO anon
  USING (false)
  WITH CHECK (false);

CREATE POLICY checkout_payment_attempts_deny_authenticated
  ON public.checkout_payment_attempts
  FOR ALL TO authenticated
  USING (false)
  WITH CHECK (false);
