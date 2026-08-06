-- Geo telemetry: IP-derived country/region/city on usage_log
-- Run: wrangler d1 execute vidrank --remote --file=migrations/003_geo.sql

ALTER TABLE usage_log ADD COLUMN country TEXT;
ALTER TABLE usage_log ADD COLUMN region TEXT;
ALTER TABLE usage_log ADD COLUMN city TEXT;
CREATE INDEX IF NOT EXISTS idx_usage_log_country_ts ON usage_log(country, ts DESC);
