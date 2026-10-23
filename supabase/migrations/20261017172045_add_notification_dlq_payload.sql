-- Preserve custom Web Push campaign options for durable retries.
ALTER TABLE public.notification_dlq
  ADD COLUMN IF NOT EXISTS payload jsonb NOT NULL DEFAULT '{}'::jsonb;
