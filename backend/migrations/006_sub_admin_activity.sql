-- Sub-admin activity log: every user-table action a sub-admin takes
-- (tier change, activate/suspend, quota reset, usage set) is recorded here
-- so the super admin can audit who did what. Username/email are snapshotted
-- so history survives sub-admin/user deletion.
-- Run: wrangler d1 execute vidrank --remote --file=migrations/006_sub_admin_activity.sql
CREATE TABLE IF NOT EXISTS sub_admin_activity (
  id                 TEXT PRIMARY KEY,
  sub_admin_id       TEXT NOT NULL,
  sub_admin_username TEXT NOT NULL,
  action             TEXT NOT NULL,
  target_uid         TEXT NOT NULL,
  target_email       TEXT,
  details            TEXT,
  created_at         INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_created ON sub_admin_activity (created_at DESC);
