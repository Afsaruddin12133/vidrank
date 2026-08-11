-- Sub-admin accounts: username/password logins with limited (users-table only)
-- access. Created/managed by the super admin. Passwords stored as PBKDF2 hashes.
-- Run: wrangler d1 execute vidrank --remote --file=migrations/005_sub_admins.sql
CREATE TABLE IF NOT EXISTS sub_admins (
  id         TEXT PRIMARY KEY,
  username   TEXT NOT NULL UNIQUE,
  pass_hash  TEXT NOT NULL,
  is_active  INTEGER NOT NULL DEFAULT 1,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
