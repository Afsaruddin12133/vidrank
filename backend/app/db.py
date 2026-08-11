"""D1 data access + batched flusher (plan/DATABASE.md).

Free-tier D1 write discipline: all writes flow through BatchedFlusher
(~20 rows/flush) so per-request writes never hit D1's ~1000/day free quota.
Reads (`SELECT`) are cheap and unlimited-ish (D1 read quota ~5M/day).

Only the flusher writes. Individual `db` helpers are READ-ONLY by convention.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

from . import contracts as C

BATCH_SIZE = 20


def _row(cols: list[str], values: list[Any]) -> dict[str, Any] | None:
    if not cols:
        return None
    return {c: v for c, v in zip(cols, values)}


async def _fetch_all(env, sql: str, *params) -> list[dict[str, Any]]:
    stmt = env.DB.prepare(sql).bind(*params)
    try:
        res = await stmt.all()
    except TypeError:  # sync worker shim: .all() returns directly
        res = stmt.all()
    
    # Handle both D1 format and our dev_server format
    if hasattr(res, "results"):
        # Results are already dicts from our dev_server
        return res.results or []
    else:
        # Fallback for other formats
        return list(res) if res else []


async def _fetch_one(env, sql: str, *params) -> dict[str, Any] | None:
    rows = await _fetch_all(env, sql, *params)
    return rows[0] if rows else None


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def get_effective_tier(user: dict[str, Any] | None) -> str:
    """Return user tier ('free' or 'pro').

    If user is 'pro' but expires_at is in the past, automatically falls back to 'free'.
    """
    if not user:
        return "free"
    tier = (user.get("tier") or "free").strip().lower()
    if tier == "pro":
        expires_at = user.get("expires_at")
        if expires_at:
            try:
                import time
                from datetime import datetime
                exp_ts = None
                if isinstance(expires_at, (int, float)):
                    exp_ts = float(expires_at)
                elif isinstance(expires_at, str):
                    s = expires_at.strip()
                    if s.replace(".", "", 1).isdigit():
                        exp_ts = float(s)
                    else:
                        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                        exp_ts = dt.timestamp()
                if exp_ts is not None and time.time() > exp_ts:
                    return "free"
            except Exception:
                pass
    return tier


async def get_user(env, uid: str) -> dict[str, Any] | None:
    return await _fetch_one(
        env, "SELECT firebase_uid, email, tier, is_active, synced_at, balance, "
        "subscription_id, expires_at, referred_by, usage_count, last_usage_reset, "
        "name, photo_url, referred_by_sub_id "
        "FROM users WHERE firebase_uid = ?1",
        uid,
    )


async def upsert_user(env, user: dict) -> None:
    """Insert or replace a user row from Firestore (webhook / login sync path).

    `user` keys: firebase_uid, email, tier, is_active, synced_at, and optional
    balance, subscription_id, expires_at, referred_by, usage_count,
    last_usage_reset, name, photo_url, referred_by_sub_id.
    """
    await env.DB.prepare(
        "INSERT OR REPLACE INTO users (firebase_uid, email, tier, is_active, synced_at, "
        "balance, subscription_id, expires_at, referred_by, usage_count, last_usage_reset, "
        "name, photo_url, referred_by_sub_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    ).bind(
        user["firebase_uid"], user["email"], user["tier"], user.get("is_active", 1),
        user.get("synced_at", 0), user.get("balance"), user.get("subscription_id"),
        user.get("expires_at"), user.get("referred_by"), user.get("usage_count", 0),
        user.get("last_usage_reset"), user.get("name", ""), user.get("photo_url"),
        user.get("referred_by_sub_id"),
    ).run()


async def get_plan(env, plan_id: str) -> dict[str, Any] | None:
    return await _fetch_one(
        env, "SELECT plan_id, daily_limit, synced_at FROM plans WHERE plan_id = ?1", plan_id,
    )


async def set_user_tier(env, uid: str, tier: str) -> None:
    await env.DB.prepare("UPDATE users SET tier = ?1 WHERE firebase_uid = ?2").bind(tier, uid).run()


async def set_user_status(env, uid: str, is_active: int) -> None:
    await env.DB.prepare("UPDATE users SET is_active = ?1 WHERE firebase_uid = ?2").bind(is_active, uid).run()


# --------------------------------------------------------------------------- #
# Free-tier quota configuration (admin-configurable, served by /v1/me)
# --------------------------------------------------------------------------- #
async def get_free_quota(env) -> dict[str, Any]:
    try:
        row = await _fetch_one(env, "SELECT value FROM app_settings WHERE key = ?1", "free_quota")
        cfg = json.loads((row or {}).get("value") or "{}")
    except Exception:
        cfg = {}
    return {
        "limit": int(cfg.get("limit") or C.DEFAULT_FREE_DAILY_LIMIT),
        "cadence": cfg.get("cadence", C.CADENCE_DAILY),
        "window_days": int(cfg.get("window_days") or 0),
    }


async def set_free_quota(env, limit: int, cadence: str, window_days: int) -> None:
    await env.DB.prepare(
        "INSERT OR REPLACE INTO app_settings (key, value) VALUES (?,?)"
    ).bind(
        "free_quota", json.dumps({"limit": limit, "cadence": cadence, "window_days": window_days})
    ).run()


# --------------------------------------------------------------------------- #
# Sub-admin accounts (users-table managers, created by the super admin)
# --------------------------------------------------------------------------- #
async def list_sub_admins(env) -> list[dict[str, Any]]:
    return await _fetch_all(
        env,
        "SELECT id, username, is_active, created_at, updated_at FROM sub_admins ORDER BY created_at ASC",
    )


async def get_sub_admin(env, sub_id: str) -> dict[str, Any] | None:
    return await _fetch_one(env, "SELECT * FROM sub_admins WHERE id = ?1", sub_id)


async def get_sub_admin_by_username(env, username: str) -> dict[str, Any] | None:
    return await _fetch_one(env, "SELECT * FROM sub_admins WHERE username = ?1", username)


async def add_sub_admin(env, *, sub_id: str, username: str, pass_hash: str) -> None:
    now = int(time.time())
    await env.DB.prepare(
        "INSERT INTO sub_admins (id, username, pass_hash, is_active, created_at, updated_at) "
        "VALUES (?,?,?,1,?,?)"
    ).bind(sub_id, username, pass_hash, now, now).run()


async def update_sub_admin(env, sub_id: str, fields: dict) -> None:
    cols, params = [], []
    for key in ("username", "pass_hash", "is_active"):
        if key in fields and fields[key] is not None:
            cols.append(f"{key}=?")
            params.append(fields[key])
    if not cols:
        return
    cols.append("updated_at=?")
    params.append(int(time.time()))
    params.append(sub_id)
    await env.DB.prepare(f"UPDATE sub_admins SET {', '.join(cols)} WHERE id=?").bind(*params).run()


async def delete_sub_admin(env, sub_id: str) -> None:
    await env.DB.prepare("DELETE FROM sub_admins WHERE id=?").bind(sub_id).run()


async def add_sub_admin_activity(env, *, sub_admin_id: str, sub_admin_username: str,
                                 action: str, target_uid: str,
                                 target_email: str | None = None,
                                 details: dict | None = None) -> None:
    """Append one audit entry for a sub-admin's user-table action."""
    await env.DB.prepare(
        "INSERT INTO sub_admin_activity "
        "(id, sub_admin_id, sub_admin_username, action, target_uid, target_email, details, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)"
    ).bind(
        str(uuid.uuid4()), sub_admin_id, sub_admin_username, action, target_uid,
        target_email, json.dumps(details) if details else None, int(time.time()),
    ).run()


async def list_sub_admin_activity(env, limit: int = 100) -> list[dict[str, Any]]:
    return await _fetch_all(
        env,
        "SELECT * FROM sub_admin_activity ORDER BY created_at DESC LIMIT ?1",
        max(1, min(limit, 500)),
    )


def _activity_filter(q: str | None, sub_admin: str | None) -> tuple[str, list[Any]]:
    conds, params = [], []
    if sub_admin and sub_admin.strip() and sub_admin.strip().lower() != "all":
        conds.append("LOWER(sub_admin_username) = ?")
        params.append(sub_admin.strip().lower())
    if q and q.strip():
        conds.append("(LOWER(sub_admin_username) LIKE ? OR LOWER(action) LIKE ? OR LOWER(target_uid) LIKE ? OR LOWER(COALESCE(target_email, '')) LIKE ?)")
        like = f"%{q.strip().lower()}%"
        params += [like, like, like, like]
    return (f"WHERE {' AND '.join(conds)}" if conds else ""), params


async def count_sub_admin_activity(env, q: str | None = None, sub_admin: str | None = None) -> int:
    where, params = _activity_filter(q, sub_admin)
    row = await _fetch_one(env, f"SELECT COUNT(*) AS n FROM sub_admin_activity {where}", *params)
    return int((row or {}).get("n") or 0)


async def list_sub_admin_activity_paged(env, q: str | None = None, sub_admin: str | None = None,
                                       page: int = 1, page_size: int = 25) -> list[dict[str, Any]]:
    where, filter_params = _activity_filter(q, sub_admin)
    offset = max(0, (page - 1) * page_size)
    params = filter_params + [page_size, offset]
    return await _fetch_all(
        env,
        "SELECT id, sub_admin_id, sub_admin_username, action, target_uid, target_email, details, created_at "
        f"FROM sub_admin_activity {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        *params,
    )



async def list_enabled_accounts(env) -> list[dict[str, Any]]:
    return await _fetch_all(
        env,
        "SELECT id, provider, label, key_enc, daily_limit, rpm_limit, created_at "
        "FROM accounts WHERE enabled = 1",
    )


async def list_accounts(env) -> list[dict[str, Any]]:
    return await _fetch_all(
        env,
        "SELECT id, provider, label, key_enc, daily_limit, rpm_limit, enabled, created_at "
        "FROM accounts ORDER BY created_at DESC",
    )


def _account_filter(q: str | None, provider: str | None) -> tuple[str, list[Any]]:
    conds, params = [], []
    if provider and provider.strip() and provider.strip().lower() != "all":
        conds.append("LOWER(provider) = ?")
        params.append(provider.strip().lower())
    if q and q.strip():
        conds.append("(LOWER(label) LIKE ? OR LOWER(id) LIKE ?)")
        like = f"%{q.strip().lower()}%"
        params += [like, like]
    return (f"WHERE {' AND '.join(conds)}" if conds else ""), params


async def count_accounts(env, q: str | None = None, provider: str | None = None) -> int:
    where, params = _account_filter(q, provider)
    row = await _fetch_one(env, f"SELECT COUNT(*) AS n FROM accounts {where}", *params)
    return int((row or {}).get("n") or 0)


async def list_accounts_paged(env, q: str | None = None, provider: str | None = None,
                             page: int = 1, page_size: int = 10) -> list[dict[str, Any]]:
    where, filter_params = _account_filter(q, provider)
    offset = max(0, (page - 1) * page_size)
    params = filter_params + [page_size, offset]
    return await _fetch_all(
        env,
        "SELECT id, provider, label, key_enc, daily_limit, rpm_limit, enabled, created_at "
        f"FROM accounts {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        *params,
    )



async def get_account(env, account_id: str) -> dict[str, Any] | None:
    return await _fetch_one(
        env,
        "SELECT id, provider, label, key_enc, daily_limit, rpm_limit, enabled, created_at FROM accounts WHERE id = ?1",
        account_id,
    )


async def add_account(env, account: dict) -> None:
    await env.DB.prepare(
        "INSERT INTO accounts (id, provider, label, key_enc, daily_limit, rpm_limit, "
        "enabled, created_at) VALUES (?,?,?,?,?,?,?,?)"
    ).bind(
        account["id"], account["provider"], account.get("label"),
        account["key_enc"], account["daily_limit"], account["rpm_limit"],
        account.get("enabled", 1), account.get("created_at", 0),
    ).run()


async def update_account(env, account_id: str, fields: dict) -> None:
    """Update editable account fields: label, daily_limit, rpm_limit, enabled, key_enc."""
    cols, params = [], []
    for key in ("label", "daily_limit", "rpm_limit", "enabled", "key_enc"):
        if key in fields and fields[key] is not None:
            cols.append(f"{key}=?")
            params.append(fields[key])
    if not cols:
        return
    params.append(account_id)
    await env.DB.prepare(
        f"UPDATE accounts SET {', '.join(cols)} WHERE id=?").bind(*params).run()


async def delete_account(env, account_id: str) -> None:
    await env.DB.prepare("DELETE FROM accounts WHERE id=?").bind(account_id).run()


def _today_utc_ts() -> int:
    return int(time.time() // 86400) * 86400


async def list_users(env, tier: str | None = None) -> list[dict[str, Any]]:
    today_ts = _today_utc_ts()
    if tier:
        return await _fetch_all(
            env,
            "SELECT u.firebase_uid, u.email, u.tier, u.is_active, u.synced_at, u.balance, "
            "u.subscription_id, u.expires_at, u.name, u.photo_url, "
            "COALESCE(l.today_cnt, 0) AS usage_count "
            "FROM users u LEFT JOIN ("
            "  SELECT user_id, COUNT(*) AS today_cnt FROM usage_log "
            "  WHERE ts >= ?1 AND (status < 400 OR status = 200 OR status = '200' OR status = 'ok') "
            "  GROUP BY user_id"
            ") l ON u.firebase_uid = l.user_id "
            "WHERE u.tier = ?2 ORDER BY u.synced_at DESC",
            today_ts, tier,
        )
    return await _fetch_all(
        env,
        "SELECT u.firebase_uid, u.email, u.tier, u.is_active, u.synced_at, u.balance, "
        "u.subscription_id, u.expires_at, u.name, u.photo_url, "
        "COALESCE(l.today_cnt, 0) AS usage_count "
        "FROM users u LEFT JOIN ("
        "  SELECT user_id, COUNT(*) AS today_cnt FROM usage_log "
        "  WHERE ts >= ?1 AND (status < 400 OR status = 200 OR status = '200' OR status = 'ok') "
        "  GROUP BY user_id"
        ") l ON u.firebase_uid = l.user_id "
        "ORDER BY u.synced_at DESC",
        today_ts,
    )


async def set_user_tier(env, uid: str, tier: str) -> None:
    await env.DB.prepare("UPDATE users SET tier=?1 WHERE firebase_uid=?2") \
        .bind(tier, uid).run()


def _user_filter(q: str | None, tier: str | None) -> tuple[str, list[Any]]:
    conds, params = [], []
    if tier in ("free", "pro"):
        conds.append("u.tier=?")
        params.append(tier)
    if q:
        conds.append("(u.email LIKE ? OR u.name LIKE ? OR u.firebase_uid LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like]
    return (f"WHERE {' AND '.join(conds)}" if conds else ""), params


async def count_users(env, q: str | None = None, tier: str | None = None) -> int:
    where, params = _user_filter(q, tier)
    row = await _fetch_one(env, f"SELECT COUNT(*) AS n FROM users u {where}", *params)
    return int((row or {}).get("n") or 0)


async def list_users_paged(env, q: str | None = None, tier: str | None = None,
                           page: int = 1, page_size: int = 25) -> list[dict[str, Any]]:
    today_ts = _today_utc_ts()
    where, filter_params = _user_filter(q, tier)
    params = [today_ts] + filter_params + [page_size, max(0, (page - 1) * page_size)]
    return await _fetch_all(
        env,
        "SELECT u.firebase_uid, u.email, u.tier, u.is_active, u.synced_at, u.balance, "
        "u.subscription_id, u.expires_at, u.name, u.photo_url, "
        "COALESCE(l.today_cnt, 0) AS usage_count "
        "FROM users u LEFT JOIN ("
        "  SELECT user_id, COUNT(*) AS today_cnt FROM usage_log "
        "  WHERE ts >= ?1 AND (status < 400 OR status = 200 OR status = '200' OR status = 'ok') "
        "  GROUP BY user_id"
        ") l ON u.firebase_uid = l.user_id "
        f"{where} ORDER BY u.synced_at DESC LIMIT ? OFFSET ?",
        *params,
    )


async def get_usage_days(env, days: int) -> list[dict[str, Any]]:
    """Site-wide daily rollup, aggregated LIVE from usage_log (rollup tables are
    not written by anything; actual telemetry lives only in usage_log)."""
    cutoff = int(time.time()) - days * 86400
    return await _fetch_all(
        env,
        "SELECT substr(date(ts,'unixepoch'),1,10) AS day, "
        " COUNT(*) AS total_requests, "
        " SUM(CASE WHEN COALESCE(u.tier,'free')='pro' THEN 1 ELSE 0 END) AS pro_requests, "
        " SUM(CASE WHEN COALESCE(u.tier,'free')='free' THEN 1 ELSE 0 END) AS free_requests, "
        " SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) AS cache_hits, "
        " SUM(CASE WHEN status>=400 THEN 1 ELSE 0 END) AS errors, "
        " AVG(latency_ms) AS avg_latency_ms "
        "FROM usage_log l LEFT JOIN users u ON u.firebase_uid=l.user_id "
        "WHERE l.ts>=?1 GROUP BY day ORDER BY day DESC LIMIT ?2",
        cutoff, days,
    )


async def get_account_usage_days(env, account_id: str, days: int) -> list[dict[str, Any]]:
    """Per-account daily usage, aggregated live from usage_log."""
    cutoff = int(time.time()) - days * 86400
    return await _fetch_all(
        env,
        "SELECT date(ts,'unixepoch') AS day, COUNT(*) AS requests, "
        " SUM(CASE WHEN status>=400 THEN 1 ELSE 0 END) AS errors, "
        " AVG(latency_ms) AS avg_latency_ms "
        "FROM usage_log WHERE account_id=?1 AND ts>=?2 GROUP BY day ORDER BY day DESC LIMIT ?3",
        account_id, cutoff, days,
    )


async def set_account_enabled(env, account_id: str, enabled: bool) -> None:
    await env.DB.prepare("UPDATE accounts SET enabled=?1 WHERE id=?2") \
        .bind(int(enabled), account_id).run()


# --------------------------------------------------------------------------- #
# Batched writer (the ONLY path that writes)
# --------------------------------------------------------------------------- #
class BatchedFlusher:
    """Accumulates rows and flushes to D1 in ~BATCH_SIZE chunks. One shared
    instance per worker request is enough; use one global here."""

    def __init__(self, env) -> None:
        self._env = env
        self._usage: list[tuple] = []  # (user_id, account_id, model, pt, ct, cache_hit, latency, status, ts, err, country, region, city)
        self.geo: tuple = (None, None, None)  # set per-request by middleware (request.cf)

    def log_usage(self, *, user_id: str, account_id: str | None, model: str,
                  prompt_tokens: int = 0, completion_tokens: int = 0,
                  cache_hit: bool = False, latency_ms: int | None = None,
                  status: int = 200, ts: int, error_msg: str | None = None,
                  geo: tuple | None = None) -> None:
        country, region, city = geo or self.geo
        self._usage.append(
            (user_id, account_id, model, prompt_tokens, completion_tokens,
             int(cache_hit), latency_ms, status, ts, error_msg, country, region, city)
        )
        if len(self._usage) >= BATCH_SIZE:
            self.flush_now()

    async def flush_now(self) -> None:
        if not self._usage:
            return
        batch, self._usage = self._usage, []
        sql = (
            "INSERT INTO usage_log "
            "(user_id, account_id, model, prompt_tokens, completion_tokens, "
            " cache_hit, latency_ms, status, ts, error_msg, country, region, city) VALUES "
            + ",".join("(?,?,?,?,?,?,?,?,?,?,?,?,?)" for _ in batch)
        )
        params: list[Any] = []
        for row in batch:
            params.extend(row)
        try:
            await self._env.DB.prepare(sql).bind(*params).run()
        except Exception:
            pass  # best-effort telemetry; never fail a user request on it

    async def aclose(self) -> None:
        await self.flush_now()


# Rollups are scheduled (cron/alarm), 1 upsert/day each — cheap, so not batched.
async def upsert_daily_summary(env, day: str, total: int, free: int, pro: int,
                               cache_hits: int, errors: int, avg_latency: int) -> None:
    await env.DB.prepare(
        "INSERT OR REPLACE INTO usage_daily "
        "(day, total_requests, free_requests, pro_requests, cache_hits, errors, avg_latency_ms) "
        "VALUES (?,?,?,?,?,?,?)"
    ).bind(day, total, free, pro, cache_hits, errors, avg_latency).run()


async def upsert_account_daily(env, account_id: str, day: str, requests: int,
                               errors: int, avg_latency: int) -> None:
    await env.DB.prepare(
        "INSERT OR REPLACE INTO account_usage_daily "
        "(account_id, day, requests, errors, avg_latency_ms) VALUES (?,?,?,?,?)"
    ).bind(account_id, day, requests, errors, avg_latency).run()


# --------------------------------------------------------------------------- #
# Memory graph (plan/MEMORY-GRAPH.md) — batched writes
# --------------------------------------------------------------------------- #
async def get_memory_node(env, user_id: str, node_type: str, node_id: str) -> dict[str, Any] | None:
    return await _fetch_one(
        env,
        "SELECT payload, ts FROM memory_graph WHERE user_id=?1 AND node_type=?2 AND node_id=?3",
        user_id, node_type, node_id,
    )


async def put_memory_node(env, *, user_id: str, node_type: str, node_id: str,
                          parent_id: str | None, payload: dict, ts: int) -> None:
    await env.DB.prepare(
        "INSERT OR REPLACE INTO memory_graph "
        "(user_id, node_type, node_id, parent_id, payload, ts) VALUES (?,?,?,?,?,?)"
    ).bind(user_id, node_type, node_id, parent_id, json.dumps(payload), ts).run()


async def list_subscriptions(env) -> list[dict]:
    """Fetch all subscription requests ordered by created_at DESC."""
    try:
        return await _fetch_all(
            env,
            "SELECT id, user_id, user_name, user_email, plan, bkash_number, "
            "transaction_id, amount_bdt, amount_usd, requested_at, status, "
            "subscription_id, created_at FROM subscriptions ORDER BY created_at DESC"
        )
    except Exception:
        return []


async def update_subscription_status(env, sub_id: str, status: str) -> None:
    """Update subscription request status."""
    try:
        await env.DB.prepare("UPDATE subscriptions SET status=?1 WHERE id=?2") \
            .bind(status, sub_id).run()
    except Exception:
        pass