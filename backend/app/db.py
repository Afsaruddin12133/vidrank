"""D1 data access + batched flusher (plan/DATABASE.md).

Free-tier D1 write discipline: all writes flow through BatchedFlusher
(~20 rows/flush) so per-request writes never hit D1's ~1000/day free quota.
Reads (`SELECT`) are cheap and unlimited-ish (D1 read quota ~5M/day).

Only the flusher writes. Individual `db` helpers are READ-ONLY by convention.
"""
from __future__ import annotations

import json
import time
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


async def list_enabled_accounts(env) -> list[dict[str, Any]]:
    return await _fetch_all(
        env,
        "SELECT id, provider, label, key_enc, daily_limit, rpm_limit, created_at "
        "FROM accounts WHERE enabled = 1",
    )


async def list_accounts(env) -> list[dict[str, Any]]:
    return await _fetch_all(
        env,
        "SELECT id, provider, label, daily_limit, rpm_limit, enabled, created_at "
        "FROM accounts ORDER BY created_at DESC",
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
    """Update editable account fields: label, daily_limit, rpm_limit, enabled."""
    cols, params = [], []
    for key in ("label", "daily_limit", "rpm_limit", "enabled"):
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


async def list_users(env, tier: str | None = None) -> list[dict[str, Any]]:
    if tier:
        return await _fetch_all(
            env,
            "SELECT firebase_uid, email, tier, is_active, synced_at, balance, "
            "subscription_id, expires_at, usage_count, name "
            "FROM users WHERE tier=?1 ORDER BY synced_at DESC",
            tier,
        )
    return await _fetch_all(
        env,
        "SELECT firebase_uid, email, tier, is_active, synced_at, balance, "
        "subscription_id, expires_at, usage_count, name "
        "FROM users ORDER BY synced_at DESC",
    )


async def set_user_tier(env, uid: str, tier: str) -> None:
    await env.DB.prepare("UPDATE users SET tier=?1 WHERE firebase_uid=?2") \
        .bind(tier, uid).run()


async def get_usage_days(env, days: int) -> list[dict[str, Any]]:
    return await _fetch_all(
        env,
        "SELECT * FROM usage_daily ORDER BY day DESC LIMIT ?1", days,
    )


async def get_account_usage_days(env, account_id: str, days: int) -> list[dict[str, Any]]:
    return await _fetch_all(
        env,
        "SELECT * FROM account_usage_daily WHERE account_id=?1 ORDER BY day DESC LIMIT ?2",
        account_id, days,
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
        self._usage: list[tuple] = []  # (user_id, account_id, model, pt, ct, cache_hit, latency, status, ts)

    def log_usage(self, *, user_id: str, account_id: str | None, model: str,
                  prompt_tokens: int = 0, completion_tokens: int = 0,
                  cache_hit: bool = False, latency_ms: int | None = None,
                  status: int = 200, ts: int) -> None:
        self._usage.append(
            (user_id, account_id, model, prompt_tokens, completion_tokens,
             int(cache_hit), latency_ms, status, ts)
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
            " cache_hit, latency_ms, status, ts) VALUES "
            + ",".join("(?,?,?,?,?,?,?,?,?)" for _ in batch)
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