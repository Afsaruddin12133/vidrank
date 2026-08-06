"""Per-account Rate State (plan/ROUTING.md).

A Durable Object per account, tracking:
  - sliding-window RPM (60s), daily counter + rollover
  - cooldown timer + reason
  - health EMA: 0.7*success_rate + 0.2*latency_score + 0.1*stability
  - header-truth (x-ratelimit-remaining-*) overrides config when fresh (<5min)

All state lives in DO memory/storage — NO D1 writes per request.
"""
from __future__ import annotations

import time

from . import contracts as C
try:
    from workers import DurableObject  # type: ignore
except Exception:
    DurableObject = object

WINDOW_S = 60
HEADER_FRESH_S = 300
COOLDOWN_DEFAULT_S = 30
HEALTH_FLOOR = 0.3


class RateStateDO(DurableObject):
    """Cloudflare Durable Object. One instance per account id (storage key = id)."""

    def __init__(self, state, env) -> None:
        self.state = state
        self.env = env
        self._hits: list[int] = []          # rpm window timestamps
        self._used_today: int = 0
        self._day: str = ""                  # YYYY-MM-DD
        self._cooldown_until: float = 0.0
        self._health: float = 1.0
        self._latencies: list[int] = []      # last N for p50
        self._failures: int = 0
        self._last_used: int = 0
        self._header_remaining: int | None = None
        self._header_reset: int | None = None
        self._header_ts: float = 0.0
        self._rpm_limit: int = 30

    # -- helpers ------------------------------------------------------------- #
    def _day_of(self, now: int) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime(now))

    def _p50(self) -> float:
        if not self._latencies:
            return 0.0
        s = sorted(self._latencies)[:50]
        mid = len(s) // 2
        return float(s[mid]) if len(s) % 2 else float((s[mid - 1] + s[mid]) / 2)

    def _latency_score(self) -> float:
        return max(0.0, 1.0 - self._p50() / 2000.0)

    def _roll_daily(self, now: int) -> None:
        today = self._day_of(now)
        if today != self._day:
            self._day = today
            self._used_today = 0

    def _prune_window(self, now: int) -> None:
        self._hits = [t for t in self._hits if now - t < WINDOW_S]

    # -- RPCs ----------------------------------------------------------------- #
    async def observe_response(self, account_id: str, *, status: int,
                               rate_headers: dict, latency_ms: int) -> dict:
        now = int(time.time())
        self._roll_daily(now)
        self._prune_window(now)

        # header truth
        if rate_headers.get("remaining") is not None:
            self._header_remaining = rate_headers["remaining"]
            self._header_ts = now
        if rate_headers.get("reset") is not None:
            self._header_reset = rate_headers["reset"]

        ok = status < 400
        if ok:
            self._hits.append(now)
            self._used_today += 1
            self._last_used = now
            if latency_ms is not None:
                self._latencies.append(latency_ms)
                self._latencies = self._latencies[-200:]
        else:
            self._failures += 1
            cooldown = rate_headers.get("retry_after") or (
                (self._header_reset or now) - now if self._header_reset else 0
            ) or COOLDOWN_DEFAULT_S
            self._cooldown_until = now + max(5, cooldown)

        # health EMA
        success_rate = 1.0 if self._failures == 0 else max(
            0.0, 1.0 - self._failures / max(1, self._failures + len(self._hits))
        )
        self._health = 0.7 * success_rate + 0.2 * self._latency_score() + 0.1 * 0.9
        if self._health < HEALTH_FLOOR:
            self._cooldown_until = max(self._cooldown_until, now + COOLDOWN_DEFAULT_S)

        return await self.get_live()

    async def get_health(self) -> dict:
        return {
            "health": round(self._health, 3),
            "cooldown_until": int(self._cooldown_until),
            "last_latency_ms": self._latencies[-1] if self._latencies else None,
            "failures": self._failures,
        }

    async def get_live(self) -> dict:
        now = int(time.time())
        self._roll_daily(now)
        self._prune_window(now)
        return {
            "used_today": self._used_today,
            "rpm_window_count": len(self._hits),
            "cooldown_until": int(self._cooldown_until),
            "last_used": self._last_used,
            "header_remaining": self._header_remaining,
            "health": round(self._health, 3),
        }

    async def select_weight(self, day: str, now: int, rpm_limit: int | None = None) -> float:
        """Weight for the routing formula. 0.0 => excluded (cooldown/degraded)."""
        if rpm_limit:
            self._rpm_limit = rpm_limit
        if now < self._cooldown_until or self._health < HEALTH_FLOOR:
            return 0.0
        self._prune_window(now)
        remaining = self._header_remaining if (
            self._header_remaining is not None
            and now - self._header_ts < HEADER_FRESH_S
        ) else None
        daily_remaining = remaining if remaining is not None else self._used_today
        headroom = max(0.1, 1.0 - min(1.0, daily_remaining / 14400.0))
        rpm_headroom = max(0.1, 1.0 - min(1.0, len(self._hits) / max(1, self._rpm_limit)))
        return self._health * headroom * rpm_headroom

    async def note_cooldown(self, seconds: int) -> None:
        self._cooldown_until = time.time() + max(5, int(seconds))
