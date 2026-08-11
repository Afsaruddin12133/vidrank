"""VIDRANK shared contracts — SINGLE SOURCE OF TRUTH.

Every module in app/ codes against THIS file. Binding names, secrets, tier keys,
and the public function/method signatures each module must export are defined
here so that modules written independently (in parallel) integrate cleanly.

Consumption rule:
  - `env` is the Cloudflare Worker `Env` object (bindings named below).
  - We NEVER read `env` attributes by guessing — every binding is a constant.

Only deterministic code. No Date.now() math in composition path (not applicable);
timestamps are wall-clock by design for quota/memory.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Binding names (wrangler.toml MUST match these exactly)
# --------------------------------------------------------------------------- #
BIND_D1       = "DB"          # D1 database
BIND_KV       = "KV"          # KV namespace (resp: / sem: / sess:)
BIND_QUOTA    = "QUOTA"       # Durable Object class QuotaDO
BIND_RATESTATE = "RATESTATE"  # Durable Object class RateStateDO
BIND_FREEQ    = "FREE_QUEUE"  # Cloudflare Queue producers
BIND_PROQ     = "PRO_QUEUE"
BIND_AI       = "AI"          # Workers AI (embeddings)

# Secret names (env.ENCRYPTION_KEY, env.JWT_SECRET, etc.)
SECRET_ENCRYPTION_KEY = "ENCRYPTION_KEY"
SECRET_ADMIN_PASS  = "ADMIN_PASS"  # password that unlocks /admin/* (env secret)
SECRET_ADMIN_TOKEN = "ADMIN_TOKEN_KEY"  # HMAC key signing admin session tokens

# Browser CORS allowlist (CSV Cloudflare var). Empty = deny all browser origins.
# Proxied API keys never reach the client; restricting origins stops drive-by
# sites from abusing the proxy pool.
ALLOWED_ORIGINS: list[str] = [
    o.strip() for o in (__import__("os").environ.get("ALLOWED_ORIGINS", "") or "").split(",")
    if o.strip()
]

# KV key prefixes ------------------------------------------------------------------- #
KV_RESP = "resp:"   # exact response cache, TTL 1h
KV_SEM  = "sem:"    # semantic cache vectors, TTL 24h
KV_SESS = "sess:"   # Firebase JWT session blacklist (revocations)

# Tier / quota --------------------------------------------------------------------- #
TIER_FREE = "free"
TIER_PRO  = "pro"
DEFAULT_FREE_DAILY_LIMIT = 10  # plan says 10/day free ("extension business plan")

# Free-tier quota cadence (admin-configurable via /admin/free-quota):
#   daily        — limit per day, resets each day (optional window_days cap)
#   never        — one-time total limit, never resets
#   unlimited    — unlimited generations (like pro)
CADENCE_DAILY     = "daily"
CADENCE_NEVER     = "never"
CADENCE_UNLIMITED = "unlimited"
CADENCE_DEFAULT   = CADENCE_DAILY

# /v1/generate throttle curve (EXTENSION-INTEGRATION.md §3): retry_after =
# GENERATE_DELAYS[min(used, last)]s after a free generation; pro always 0.
GENERATE_DELAYS: list[int] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

# Request validation caps (abuse / cost control) ---------------------------------- #
MAX_MESSAGES = 64       # max chat messages per request
MAX_TOKENS   = 8192     # max max_tokens a client may request

# Provider defaults (used when provider headers are absent; config is the floor) --- #
GROQ_MODEL = "llama-3.1-8b-instant"
PROVIDER_DEFAULTS = {
    "groq":       {"daily_limit": 14_400, "rpm_limit": 30},
    "openrouter": {"daily_limit": 50,     "rpm_limit": 20},
}

# Request-shape ------------------------------------------------------------ #
IN_FLIGHT_CAP = 500      # global in-flight cap; above => enqueue
FALLBACK_TRIES = 3       # max retries on 429/5xx/timeout
FANOUT_MAX_PARALLEL = 8  # SoT skeleton->expand fan-out cap
FANOUT_DEADLINE_S = 25   # per-request fan-out deadline
SHORT_ANSWER_CLUE = None # reserved

# Caching -------------------------------------------------------------------
RESP_CACHE_TTL_S = 7 * 24 * 60 * 60   # resp: 7 days
SEM_CACHE_TTL_S  = 7 * 24 * 60 * 60   # sem: 7 days
SEM_COSINE_THRESHOLD = 0.90
EMBEDDING_MODEL = "@cf/baai/bge-small-en-v1.5"

# Memory graph ------------------------------------------------------------
MEM_FREE_RETAIN_SESSIONS = 3  # free user keeps last 3 sessions in graph

# =========================================================================== #
# PUBLIC INTERFACES — each module MUST expose these exact signatures.
# `env` is the Worker Env. D1 is accessed via env.<BIND_DB>.exec()/.prepare().
# =========================================================================== #

# --- db.py -----------------------------------------------------------------
# async def ping(env) -> bool
# async def get_user(env, uid: str) -> dict | None
# async def get_plan(env, plan_id: str) -> dict | None
# async def list_enabled_accounts(env) -> list[dict]
# async def get_account(env, account_id: str) -> dict | None
# async def add_account(env, account: dict) -> None
# async def set_account_enabled(env, account_id: str, enabled: bool) -> None
# class BatchedFlusher: async def flush(events)  (# ~20 rows/batch)

# --- quotas.py ----------------------------------------------------------------
# class QuotaDO(DurableObject):  # per-user quota: inc / remaining / refill
#   async def inc(self) -> dict          #  raises QuotaExceeded
#   async def remaining(self) -> int
#   async def resets_in_seconds(self) -> int
#   async def checkpoint(self) -> None   # alarm() -> D1 durable stats
# class QuotaError(Exception): ...
# async def get_quota(env, uid: str) -> "QuotaVerdict"
# QuotaVerdict = {ok: bool, remaining: int, resets_in_seconds: int, limit: int|None}

# --- ratestate.py (ROUTING.md) --------------------------------------------------
# class RateStateDO(DurableObject):
#   async def observe_response(self, account_id:str, *, status:int,
#                              rate_headers: dict, latency_ms:int) -> dict
#   async def get_health(self) -> dict
#   async def get_live(self) -> dict      # requests today, rpm window, cooldown
#   async def select_weight(self, day:str, now:int) -> float
#   async def note_cooldown(self, seconds: int)

# --- router.py --------------------------------------------------------------
# async def execute_request(env, *, user_id:str, account:dict, payload:dict)
#     -> RouterResult  # {status, content, latency_ms, account_id, cache_hit}
# async def pick_account(env, day:str, now:int) -> dict | None
#     # weighted-random over healthy accounts, fallback-run

# --- cache.py -------------------------------------------------------------
# async def get_semantic(env, user_id:str, model:str, text:str) -> str | None
# async def store_semantic(env, user_id:str, model:str, text:str, content:str)
# async def get_exact(env, key:str) -> str | None
# async def store_exact(env, key:str, content:str) -> None
# def exact_key(model:str, messages:list, temperature:float, max_tokens:int) -> str

# --- mq.py -----------------------------------------------------------------
# async def enqueue_free(env, payload:dict) -> None
# async def enqueue_pro(env, payload:dict) -> None
# async def consume_job(env, payload:dict) -> dict  # runs same router path

# --- firebase.py -----------------------------------------------------------
# async def verify_token(token:str, env) -> dict      # claims or raise
# class AuthError(Exception)

# --- sync.py -------------------------------------------------------------
# async def sync_plans(env) -> None
# async def sync_users(env) -> None

# --- admin.py ---------------------------------------------------------------
# def encrypt_key(env, epoch:str) -> str          # sync (pure)
# def decrypt_key(env, key_enc:str) -> str        # sync (pure)
# def is_admin(env, uid:str) -> bool              # sync (pure)