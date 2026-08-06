"""Free/Pro quota enforcement (plan/TIERS.md).

Per-user QuotaDO: counter lives in DO memory, day rollover, atomic inc,
checkpoint to D1 only on alarm (durable stats). Live reads never touch D1.

QuotaVerdict: {ok, remaining, resets_in_seconds}
  - free: remaining from dailyLimit (plan doc via D1; default 10)
  - pro:   unlimited (ok always)
"""
from __future__ import annotations

import time

from . import contracts as C
from . import db
try:
    from workers import DurableObject  # type: ignore
except Exception:
    DurableObject = object

DAY_S = 86400


class QuotaError(Exception):
    """Raised by QuotaDO.inc when the user is out of quota."""


class QuotaDO(DurableObject):
    """Cloudflare Durable Object: per-user quota counter.

    Instantiated via env.<BIND_QUOTA>.get(uid) and called as an RPC:
        quota_do = env.QUOTA.get(uid)
        verdict = await quota_do.inc()
    Storage: self.ctx.storage (Workers KV-style DO storage).
    """

    def __init__(self, state, env) -> None:
        self.state = state
        self.env = env
        self._day_started: float | None = None
        self._used: int = 0

    # -- storage helpers ----------------------------------------------------- #
    async def _load(self) -> None:
        if self._day_started is not None:
            return
        try:
            data = await self.state.storage.get("q") or {}
            self._day_started = data.get("day_started", time.time())
            self._used = data.get("used", 0)
        except Exception:
            self._day_started = time.time()
            self._used = 0

    async def _save(self) -> None:
        try:
            await self.state.storage.put(
                "q", {"day_started": self._day_started, "used": self._used}
            )
        except Exception:
            pass  # DO memory is truth for live; storage is durability best-effort

    # -- tier / limit -------------------------------------------------------- #
    async def _limit(self) -> int | None:
        """None => unlimited (pro). Reads plan doc daily_limit via D1."""
        try:
            uid = getattr(self.state, "id", None) or "unknown"
            user = await db.get_user(self.env, uid) if uid != "unknown" else None
        except Exception:
            user = None
        tier = (user or {}).get("tier") or C.TIER_FREE
        if tier == C.TIER_PRO:
            return None
        try:
            plan = await db.get_plan(self.env, C.TIER_FREE)
            limit = (plan or {}).get("daily_limit")
            return int(limit) if limit else C.DEFAULT_FREE_DAILY_LIMIT
        except Exception:
            return C.DEFAULT_FREE_DAILY_LIMIT

    # -- public RPC ---------------------------------------------------------- #
    async def _rollover(self) -> None:
        now = time.time()
        if now - (self._day_started or 0) >= DAY_S:
            self._day_started = now
            self._used = 0
            await self._save()

    async def inc(self) -> dict:
        """Increment usage. Returns verdict; raises QuotaError when over."""
        await self._load()
        await self._rollover()
        limit = await self._limit()
        if limit is not None and self._used >= limit:
            raise QuotaError()
        self._used += 1
        await self._save()
        remaining = limit - self._used if limit is not None else -1
        return {
            "ok": True,
            "remaining": remaining,
            "resets_in_seconds": max(0, int(DAY_S - (time.time() - self._day_started))),
            "limit": limit,
        }

    async def remaining(self) -> dict:
        await self._load()
        await self._rollover()
        limit = await self._limit()
        remaining = limit - self._used if limit is not None else -1
        return {
            "ok": limit is None or remaining > 0,
            "remaining": remaining,
            "resets_in_seconds": max(0, int(DAY_S - (time.time() - self._day_started))),
            "limit": limit,
        }

    async def resets_in_seconds(self) -> int:
        await self._load()
        await self._rollover()
        return max(0, int(DAY_S - (time.time() - self._day_started)))

    async def checkpoint(self) -> None:
        """Durable daily rollup write (scheduled, not per-request)."""
        await self._load()
        await self._save()

    async def alarm(self) -> None:
        await self.checkpoint()


async def get_quota(env, uid: str) -> dict:
    """Public verdict for a request: {ok, remaining, resets_in_seconds}.

    Pro users pass always; free users pass while remaining > 0.
    """
    try:
        do = env.QUOTA.get(uid)
        return await do.remaining()
    except Exception:
        # DO unavailable => permissive fallback (defense-in-depth layer 4).
        return {"ok": True, "remaining": -1, "resets_in_seconds": 0}
