"""Rate-limit-aware router (plan/ROUTING.md).

Weighted pick over healthy accounts + header-driven rate state + fallback chain.
The "never hit rate limit" core.
"""
from __future__ import annotations

import hashlib
import json
import random
import time

try:
    from js import fetch as js_fetch  # outbound HTTP in Python Workers
    from js import JSON as js_JSON
except ImportError:
    js_fetch = None
    js_JSON = None

from . import contracts as C
from . import db

ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
}
# Groq-only model IDs -> OpenRouter equivalents (OpenRouter rejects Groq names)
MODEL_MAP = {
    "openrouter": {
        "llama-3.3-70b-versatile": "meta-llama/llama-3.3-70b-instruct",
        "llama-3.1-8b-instant": "meta-llama/llama-3.1-8b-instruct",
    },
}
TIMEOUT_S = 55


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #
async def _account_weight(env, account: dict, now: int) -> float:
    """Ask the account's RateState DO for its routing weight (0 = skip)."""
    day = time.strftime("%Y-%m-%d", time.gmtime(now))
    try:
        do = env.RATESTATE.get(account["id"])
        res = await do.select_weight(day, now, rpm_limit=account.get("rpm_limit"))
        return float(res) if res is not None else 1.0
    except Exception:
        return 0.5  # DO unreachable => neutral weight, keep in pool


async def pick_account(env, day: str, now: int, exclude: set[str] | None = None,
                       sticky_key: str | None = None) -> dict | None:
    """Weighted-random over healthy enabled accounts. None if pool exhausted.

    sticky_key pins a stable key to one account first so Groq's per-org
    prompt cache (ROUTING.md §cost learnings) warms; falls through to
    weighted-random only when the pinned account is unhealthy.
    """
    accounts = [a for a in await db.list_enabled_accounts(env)
                if not exclude or a["id"] not in exclude]
    if not accounts:
        return None
    if sticky_key and len(accounts) > 1:
        first = accounts[_sticky_index(sticky_key, len(accounts))]
        if await _account_weight(env, first, now) > 0.15:
            return first
    weights: list[float] = []
    for a in accounts:
        w = await _account_weight(env, a, now)
        weights.append(max(w, 0.0))
    total = sum(weights)
    if total <= 0:
        return None
    choice = random.choices(accounts, weights=weights, k=1)[0]
    return choice


def _sticky_index(key: str, n: int) -> int:
    return int(hashlib.sha256(key.encode()).hexdigest(), 16) % n


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
async def _provider_post(url: str, body: dict, bearer: str, timeout_s: int = TIMEOUT_S) -> dict:
    """POST to the provider via the JS fetch API (urllib can't open sockets here).

    Returns {status, body, headers}. Raises on network failure.
    """
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {bearer}"}
    init = js_JSON.parse(json.dumps({
        "method": "POST",
        "headers": headers,
        "body": json.dumps(body),
    }))
    resp = await js_fetch(url, init)
    raw = await resp.text()
    hdrs = {}
    try:
        for k, v in resp.headers.entries():
            hdrs[str(k).lower()] = str(v)
    except Exception:
        pass
    return {"status": resp.status, "body": raw, "headers": hdrs}


def _rate_headers(headers: dict) -> dict:
    """Normalize provider headers into {remaining, reset, retry_after}."""
    out = {}
    r = headers.get("x-ratelimit-remaining-requests")
    if r is not None:
        try:
            out["remaining"] = int(r)
        except (TypeError, ValueError):
            pass
    reset = headers.get("x-ratelimit-reset")
    if reset is not None:
        try:
            out["reset"] = int(float(reset))
        except (TypeError, ValueError):
            pass
    ra = headers.get("retry-after")
    if ra is not None:
        try:
            out["retry_after"] = int(float(ra))
        except (TypeError, ValueError):
            pass
    return out


async def _observe(env, account: dict, status: int, headers: dict, latency_ms: int) -> None:
    try:
        do = env.RATESTATE.get(account["id"])
        await do.observe_response(
            account["id"], status=status,
            rate_headers=_rate_headers(headers), latency_ms=latency_ms,
        )
    except Exception:
        pass


async def execute_request(env, *, user_id: str, account: dict, payload: dict,
                          sticky_key: str | None = None) -> dict:
    """Proxy one request with fallback (<= FALLBACK_TRIES) and header observation.

    Returns RouterResult: {status, content, latency_ms, account_id, cache_hit}.
    """
    content: str = ""
    latency_ms: int = 0
    status: int = 503
    used_id: str = account["id"]
    cache_hit: bool = False
    error_msg: str = ""

    for attempt in range(max(1, C.FALLBACK_TRIES)):
        acc = account if attempt == 0 else None
        if acc is None:
            acc = await pick_account(env, time.strftime("%Y-%m-%d", time.gmtime()),
                                     int(time.time()),
                                     exclude={used_id} if used_id else None)
            if not acc:
                break

        used_id = acc["id"]
        url = ENDPOINTS.get(acc.get("provider", ""))
        if not url:
            continue
        model = payload.get("model") or C.GROQ_MODEL
        model = MODEL_MAP.get(acc.get("provider", ""), {}).get(model, model)
        body = {
            "model": model,
            "messages": payload.get("messages") or [],
            "temperature": payload.get("temperature", 0.7),
            "max_tokens": payload.get("max_tokens", 1024),
        }
        start = time.time()
        try:
            result = await _provider_post(url, body, _decode_key(env, acc), TIMEOUT_S)
            latency_ms = int((time.time() - start) * 1000)
            status = result["status"]
            raw = result["body"]
            hdrs = result["headers"]
            if status >= 400:
                error_msg = raw[:500]
            await _observe(env, acc, status, hdrs, latency_ms)
            if status == 429:
                try:
                    ra = hdrs.get("retry-after") or hdrs.get("x-ratelimit-reset")
                    if ra:
                        await env.RATESTATE.get(used_id).note_cooldown(int(float(ra)))
                    else:
                        await env.RATESTATE.get(used_id).note_cooldown(30)
                except Exception:
                    pass
            if status < 400:
                try:
                    data = json.loads(raw)
                    content = (data["choices"][0]["message"]["content"] or "").strip()
                except (KeyError, IndexError, ValueError):
                    content = raw
                break
        except Exception as e:
            latency_ms = int((time.time() - start) * 1000)
            status = 503
            import traceback
            error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"[:1500]
            print(f"[router] provider call failed for {acc.get('id')}: {error_msg}", flush=True)
            try:
                await env.RATESTATE.get(used_id).note_cooldown(10)
            except Exception:
                pass
        if status < 400:
            break

    return {
        "status": status if content else 503,
        "content": content,
        "latency_ms": latency_ms,
        "account_id": used_id,
        "cache_hit": cache_hit,
        "error_msg": error_msg,
    }


def _decode_key(env, account: dict) -> str:
    try:
        return _decode_key_impl(env, account["key_enc"])
    except Exception:
        return ""


def _decode_key_impl(env, key_enc: str) -> str:
    from . import admin
    return admin.decrypt_key(env, key_enc)