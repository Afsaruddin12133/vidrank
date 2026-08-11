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


def _self_uid(state) -> str:
    """Best-effort uid from a name-based DO id (state.id)."""
    try:
        did = getattr(state, "id", None)
        if did is None:
            return "unknown"
        name = did.name() if hasattr(did, "name") else None
        if isinstance(name, str) and name:
            return name
        s = str(did)
        return s if s and s != "unknown" else "unknown"
    except Exception:
        return "unknown"


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
        now = time.time()
        today_utc_start = (int(now) // DAY_S) * DAY_S
        if self._day_started is not None:
            if self._day_started < today_utc_start:
                self._day_started = today_utc_start
                self._used = 0
            return
        try:
            data = await self.state.storage.get("q") or {}
            stored_start = data.get("day_started", 0)
            if stored_start < today_utc_start:
                self._day_started = today_utc_start
                self._used = 0
            else:
                self._day_started = stored_start
                self._used = data.get("used", 0)
        except Exception:
            self._day_started = today_utc_start
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
        """None => unlimited (pro, or free cadence=unlimited).
        Reads admin-configurable free limit (DEFAULT fallback if unset)."""
        try:
            uid = _self_uid(self.state)
            user = await db.get_user(self.env, uid) if uid != "unknown" else None
        except Exception:
            user = None
        tier = db.get_effective_tier(user) if user else C.TIER_FREE
        if tier == C.TIER_PRO:
            return None
        try:
            cfg = await db.get_free_quota(self.env)
        except Exception:
            cfg = {}
        if cfg.get("cadence") == C.CADENCE_UNLIMITED:
            return None
        try:
            return int(cfg.get("limit") or C.DEFAULT_FREE_DAILY_LIMIT)
        except Exception:
            return C.DEFAULT_FREE_DAILY_LIMIT

    # -- public RPC ---------------------------------------------------------- #
    async def _rollover(self) -> None:
        now = time.time()
        today_utc_start = (int(now) // DAY_S) * DAY_S
        if (self._day_started or 0) < today_utc_start:
            self._day_started = today_utc_start
            self._used = 0
            await self._save()

    async def _window_expired(self) -> bool:
        """daily cadence with a non-zero window: deny after `window_days` from signup."""
        try:
            cfg = await db.get_free_quota(self.env)
            days = int(cfg.get("window_days") or 0)
            if cfg.get("cadence") != C.CADENCE_DAILY or days <= 0:
                return False
            uid = _self_uid(self.state)
            user = await db.get_user(self.env, uid) if uid != "unknown" else None
            tier = db.get_effective_tier(user) if user else C.TIER_FREE
            if tier == C.TIER_PRO:
                return False
            synced_at = (user or {}).get("synced_at") or 0
            return bool(synced_at) and time.time() - synced_at > days * DAY_S
        except Exception:
            return False

    async def _cadence_never(self) -> bool:
        try:
            cfg = await db.get_free_quota(self.env)
        except Exception:
            cfg = {}
        return cfg.get("cadence") == C.CADENCE_NEVER

    async def inc(self) -> dict:
        """Increment usage. Returns verdict; raises QuotaError when over."""
        await self._load()
        if not await self._cadence_never():
            await self._rollover()
        limit = await self._limit()
        if await self._window_expired() or (limit is not None and self._used >= limit):
            raise QuotaError()
        self._used += 1
        await self._save()
        remaining = limit - self._used if limit is not None else -1
        now = time.time()
        next_utc_day = ((int(now) // DAY_S) + 1) * DAY_S
        return {
            "ok": True,
            "remaining": remaining,
            "resets_in_seconds": max(0, int(next_utc_day - now)),
            "limit": limit,
        }

    async def remaining(self) -> dict:
        await self._load()
        if not await self._cadence_never():
            await self._rollover()
        limit = await self._limit()
        remaining = limit - self._used if limit is not None else -1
        now = time.time()
        next_utc_day = ((int(now) // DAY_S) + 1) * DAY_S
        resets = max(0, int(next_utc_day - now))
        if await self._window_expired():
            return {"ok": False, "remaining": 0, "resets_in_seconds": resets, "limit": limit}
        return {
            "ok": limit is None or remaining > 0,
            "remaining": remaining,
            "resets_in_seconds": resets,
            "limit": limit,
        }

    async def resets_in_seconds(self) -> int:
        await self._load()
        if not await self._cadence_never():
            await self._rollover()
        now = time.time()
        next_utc_day = ((int(now) // DAY_S) + 1) * DAY_S
        return max(0, int(next_utc_day - now))

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
        do = env.QUOTA.get(env.QUOTA.idFromName(uid))
        return await do.remaining()
    except Exception:
        # DO unavailable => permissive fallback (defense-in-depth layer 4).
        return {"ok": True, "remaining": -1, "resets_in_seconds": 0}
