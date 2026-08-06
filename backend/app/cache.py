"""Caching — 3 layers (plan/CACHING.md).

Layer 1 semantic (free users)  — KV `sem:{model}:{user_id}`, cos >= 0.97, TTL 24h
Layer 3 exact response        — KV `resp:{hash}` global, TTL 1h
Layer 2 (provider prompt caching) is a prompt-design concern, not code here.

Cache hit => does NOT consume user quota (handled in main.py by checking cache
before calling quota.inc).
"""
from __future__ import annotations

import hashlib
import json
import math
import time

from . import contracts as C


# --------------------------------------------------------------------------- #
# Layer 3 — exact response cache (global)
# --------------------------------------------------------------------------- #
def exact_key(model: str, messages: list, temperature: float, max_tokens: int) -> str:
    """Deterministic hash of the stable request shape (model, messages, params)."""
    stable = json.dumps(
        {"model": model, "messages": messages, "temperature": temperature,
         "max_tokens": max_tokens},
        sort_keys=True,
    )
    return hashlib.sha256(stable.encode()).hexdigest()


async def get_exact(env, key: str) -> str | None:
    try:
        val = await env.KV.get(f"{C.KV_RESP}{key}", "text")
        return val if val else None
    except Exception:
        return None


async def store_exact(env, key: str, content: str) -> None:
    try:
        await env.KV.put(f"{C.KV_RESP}{key}", content, expiration_ttl=C.RESP_CACHE_TTL_S)
    except Exception:
        pass  # cache failure never fails the request


# --------------------------------------------------------------------------- #
# Layer 1 — semantic cache (per free user)
# --------------------------------------------------------------------------- #
def _embedding_from_model(resp: dict) -> list[float]:
    data = resp.get("data") or []
    if data:
        return data[0].get("embedding") or []
    return resp.get("embedding") or []


async def _embed(env, text: str) -> list[float] | None:
    """Workers AI bge-small embedding. Returns None on failure."""
    try:
        resp = await env.AI.run(
            C.EMBEDDING_MODEL,
            {"text": [text[:8000]]},
        )
        vec = _embedding_from_model(resp)
        return vec if vec else None
    except Exception:
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def get_semantic(env, user_id: str, model: str, text: str) -> str | None:
    """Return cached response if an entry with cosine >= threshold exists."""
    try:
        vec = await _embed(env, text)
        if not vec:
            return None
        key = f"{C.KV_SEM}{model}:{user_id}"
        raw = await env.KV.get(key, "text")
        if not raw:
            return None
        entries = json.loads(raw)
        best, best_sim = None, 0.0
        for e in entries:
            sim = _cosine(vec, e.get("embedding") or [])
            if sim > best_sim:
                best, best_sim = e, sim
        if best is not None and best_sim >= C.SEM_COSINE_THRESHOLD:
            return best.get("response")
        return None
    except Exception:
        return None


async def store_semantic(env, user_id: str, model: str, text: str, content: str) -> None:
    try:
        vec = await _embed(env, text)
        if not vec:
            return
        key = f"{C.KV_SEM}{model}:{user_id}"
        raw = await env.KV.get(key, "text")
        entries = json.loads(raw) if raw else []
        entries.append({"embedding": vec, "response": content, "ts": time.time()})
        # ponytail: O(n) scan, capped at 500; upgrade to vector index if exceeded
        entries = entries[-500:]
        await env.KV.put(key, json.dumps(entries), expiration_ttl=C.SEM_CACHE_TTL_S)
    except Exception:
        pass
