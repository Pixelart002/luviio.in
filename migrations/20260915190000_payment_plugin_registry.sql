-- Runtime payment-provider/method registry.
-- Provider implementation code remains application-owned; these tables only
-- control installed-provider metadata and runtime activation.

CREATE TABLE IF NOT EXISTS public.payment_provider_plugins (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_key text NOT NULL UNIQUE CHECK (provider_key = lower(provider_key) AND length(provider_key) BETWEEN 2 AND 64),
  display_name text NOT NULL CHECK (length(trim(display_name)) BETWEEN 1 AND 120),
  enabled boolean NOT NULL DEFAULT false,
  priority integer NOT NULL DEFAULT 100 CHECK (priority >= 0 AND priority <= 10000),
  is_default boolean NOT NULL DEFAULT false,
  capabilities jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.payment_provider_methods (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_key text NOT NULL REFERENCES public.payment_provider_plugins(provider_key) ON DELETE RESTRICT,
  method_key text NOT NULL CHECK (method_key = lower(method_key) AND length(method_key) BETWEEN 2 AND 64),
  display_name text NOT NULL CHECK (length(trim(display_name)) BETWEEN 1 AND 120),
  enabled boolean NOT NULL DEFAULT true,
  priority integer NOT NULL DEFAULT 100 CHECK (priority >= 0 AND priority <= 10000),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(provider_key, method_key)
);

CREATE INDEX IF NOT EXISTS payment_provider_plugins_enabled_idx
  ON public.payment_provider_plugins(enabled, priority);
CREATE INDEX IF NOT EXISTS payment_provider_methods_enabled_idx
  ON public.payment_provider_methods(provider_key, enabled, priority);

CREATE OR REPLACE FUNCTION public.set_payment_plugin_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS payment_provider_plugins_updated_at ON public.payment_provider_plugins;
CREATE TRIGGER payment_provider_plugins_updated_at
BEFORE UPDATE ON public.payment_provider_plugins
FOR EACH ROW EXECUTE FUNCTION public.set_payment_plugin_updated_at();

DROP TRIGGER IF EXISTS payment_provider_methods_updated_at ON public.payment_provider_methods;
CREATE TRIGGER payment_provider_methods_updated_at
BEFORE UPDATE ON public.payment_provider_methods
FOR EACH ROW EXECUTE FUNCTION public.set_payment_plugin_updated_at();

-- Preserve current Stripe behaviour after migration. Admin can disable it later.
INSERT INTO public.payment_provider_plugins
  (provider_key, display_name, enabled, priority, is_default, capabilities)
VALUES
  ('stripe', 'Stripe', true, 10, true,
   '{"payment_intent":true,"refund":true,"webhook":true,"cancel":true}'::jsonb)
ON CONFLICT (provider_key) DO NOTHING;

INSERT INTO public.payment_provider_methods
  (provider_key, method_key, display_name, enabled, priority, metadata)
VALUES
  ('stripe', 'card', 'Card', true, 10, '{}'::jsonb)
ON CONFLICT (provider_key, method_key) DO NOTHING;
