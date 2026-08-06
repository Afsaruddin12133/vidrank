"""Cloudflare Queues — free/pro MQ (plan/TIERS.md).

Queues only carry bursts over the in-flight cap. The actual request runs
through the same router path (consume_job) when a consumer worker pulls it.
"""
from __future__ import annotations

from . import contracts as C


async def enqueue_free(env, payload: dict) -> None:
    try:
        await env.FREE_QUEUE.send(payload)
    except Exception:
        pass


async def enqueue_pro(env, payload: dict) -> None:
    try:
        await env.PRO_QUEUE.send(payload)
    except Exception:
        pass


async def consume_job(env, payload: dict) -> dict:
    """Deferred request path shared with main.py. payload carries {account, body, user_id}."""
    from . import router
    try:
        acct = payload.get("account")
        body = payload.get("body") or {}
        user_id = payload.get("user_id", "")
        if not acct:
            return {"status": 400, "content": "missing account", "account_id": None,
                    "latency_ms": 0, "cache_hit": False}
        return await router.execute_request(env, user_id=user_id, account=acct, payload=body)
    except Exception:
        return {"status": 500, "content": "job error", "account_id": None,
                "latency_ms": 0, "cache_hit": False}