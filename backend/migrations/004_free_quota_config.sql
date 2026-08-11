-- Admin-configurable free-tier quota (plan: dynamic free quota).
-- Single key-value row. Default = current behavior (10/day, daily reset).
-- Run: wrangler d1 execute vidrank --remote --file=migrations/004_free_quota_config.sql
CREATE TABLE IF NOT EXISTS app_settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT OR REPLACE INTO app_settings (key, value)
VALUES ('free_quota', '{"limit":10,"cadence":"daily","window_days":0}');