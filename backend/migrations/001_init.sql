-- VIDRANK D1 schema (from plan/DATABASE.md)
-- Cold durable data. Hot counters live in Durable Objects, never here.

CREATE TABLE IF NOT EXISTS users (               -- mirror of Firebase users (synced)
  firebase_uid  TEXT PRIMARY KEY,                -- Firebase Auth uid
  email         TEXT NOT NULL,
  tier          TEXT NOT NULL DEFAULT 'free',    -- free | pro (from Firestore users.plan)
  is_active     INTEGER NOT NULL DEFAULT 1,
  synced_at     INTEGER NOT NULL,
  balance       INTEGER DEFAULT 0,
  subscription_id TEXT,
  expires_at    TEXT,
  referred_by   TEXT,
  usage_count   INTEGER DEFAULT 0,
  last_usage_reset INTEGER,
  name          TEXT,
  photo_url     TEXT,
  referred_by_sub_id TEXT
);

CREATE TABLE IF NOT EXISTS plans (               -- mirror of Firestore plan docs
  plan_id       TEXT PRIMARY KEY,                -- 'free' | 'pro'
  daily_limit   INTEGER,                         -- NULL = unlimited (pro)
  synced_at     INTEGER NOT NULL,
  price         INTEGER,
  plandetails   TEXT
);

CREATE TABLE IF NOT EXISTS accounts (            -- provider credentials (unlimited, admin-added)
  id            TEXT PRIMARY KEY,
  provider      TEXT NOT NULL,                   -- 'groq' | 'openrouter'
  label         TEXT,
  key_enc       TEXT NOT NULL,                   -- AES-GCM encrypted API key
  daily_limit   INTEGER NOT NULL,                -- known provider limit, admin-editable
  rpm_limit     INTEGER NOT NULL,
  enabled       INTEGER NOT NULL DEFAULT 1,
  created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS usage_log (           -- append-only, batched writes
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id       TEXT NOT NULL,
  account_id    TEXT,
  model         TEXT NOT NULL,
  prompt_tokens INTEGER DEFAULT 0,
  completion_tokens INTEGER DEFAULT 0,
  cache_hit     INTEGER NOT NULL DEFAULT 0,
  latency_ms    INTEGER,
  status        INTEGER NOT NULL,
  ts            INTEGER NOT NULL,
  error_msg     TEXT,
  country       TEXT,
  region        TEXT,
  city          TEXT
);

CREATE TABLE IF NOT EXISTS usage_daily (         -- rollups for dashboard (1 row/day)
  day           TEXT PRIMARY KEY,                -- YYYY-MM-DD
  total_requests   INTEGER NOT NULL,
  free_requests    INTEGER NOT NULL,
  pro_requests     INTEGER NOT NULL,
  cache_hits       INTEGER NOT NULL,
  errors           INTEGER NOT NULL,
  avg_latency_ms   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS account_usage_daily ( -- per-account limit tracing (1 row/day/account)
  account_id    TEXT NOT NULL,
  day           TEXT NOT NULL,                   -- YYYY-MM-DD
  requests      INTEGER NOT NULL,
  errors        INTEGER NOT NULL,
  avg_latency_ms INTEGER NOT NULL,
  PRIMARY KEY (account_id, day)
);

CREATE TABLE IF NOT EXISTS memory_graph (        -- see plan/MEMORY-GRAPH.md
  user_id       TEXT NOT NULL,
  node_type     TEXT NOT NULL,                   -- 'entity' | 'session' | 'summary'
  node_id       TEXT NOT NULL,
  parent_id     TEXT,
  payload       TEXT NOT NULL,                   -- JSON
  ts            INTEGER NOT NULL,
  PRIMARY KEY (user_id, node_type, node_id)
);

CREATE TABLE IF NOT EXISTS app_settings (        -- admin-config key-value store
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

INSERT OR REPLACE INTO app_settings (key, value)
VALUES ('free_quota', '{"limit":10,"cadence":"daily","window_days":0}');