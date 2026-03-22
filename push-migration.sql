-- ============================================================
-- Push Notifications — DB Migration
-- Run in Supabase Dashboard → SQL Editor
-- ============================================================

-- Push subscriptions table
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    endpoint          text NOT NULL UNIQUE,
    subscription_json text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS push_subs_user_id_idx ON push_subscriptions(user_id);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_push_sub_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS push_sub_updated ON push_subscriptions;
CREATE TRIGGER push_sub_updated
  BEFORE UPDATE ON push_subscriptions
  FOR EACH ROW EXECUTE FUNCTION update_push_sub_timestamp();

SELECT 'push_subscriptions table ready' AS status;