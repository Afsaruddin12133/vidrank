"""VIDRANK FastAPI app + Cloudflare Worker entrypoint (plan/DASHBOARD.md).

Public:
  POST /v1/chat       — proxy: verify Firebase token, quota check, cache, route
  POST /v1/generate   — tags+description in one call (EXTENSION-INTEGRATION.md)
  GET  /v1/me         — tier + quota_remaining + resets_in_seconds
  GET  /v1/history    — request history
Admin (guard: admin.is_admin):
  CRUD /admin/accounts, /admin/accounts/health|usage, /admin/stats/*,
  /admin/users, /admin/plans
"""
from __future__ import annotations

import json
import re
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

from . import cache, contracts as C, db, firebase, mq, prompts, quotas, router, sync
from . import admin as admin_mod
from . import streaming, chunking  # NEW: streaming and chunking support
# DO classes must be exported from the entrypoint module for wrangler to find
# them (matches [[durable_objects.bindings]] class_name in wrangler.toml).
from .quotas import QuotaDO  # noqa: F401
from .ratestate import RateStateDO  # noqa: F401

app = FastAPI(
    title="vidrank-backend",
    docs_url=None,          # no public interactive API docs — hides schema/router
    redoc_url=None,
    openapi_url=None,
    swagger_ui_oauth2_redirect_url=None,
)

# Restrict browser origins to an explicit allowlist (empty = deny all).
# Set ALLOWED_ORIGINS as a CSV Cloudflare var: e.g. "https://app.example.com".
app.add_middleware(
    CORSMiddleware,
    allow_origins=C.ALLOWED_ORIGINS,
    allow_credentials=False,   # no cookies/session storage; Bearer in header only
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-Id"],
    max_age=86400,
)

# global in-flight counter (single worker; per-isolate)
_in_flight: int = 0


def _bindings(request: Request):
    """Worker env attached per-request by the entrypoint (asgi.fetch).

    Falls back to _NullEnv under plain uvicorn so unauthenticated requests
    short-circuit to 401/403 instead of crashing.
    """
    env = getattr(request.app.state, "env", None)
    return env if env is not None else _NullEnv()


class _NullEnv:
    """Local-dev fallback: any attribute access returns None (no bindings)."""
    def __getattr__(self, _name):
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)


async def _read_json(request: Request) -> dict | None:
    """Parse request body; None on malformed/oversized JSON (never 500)."""
    try:
        body = await request.json()
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


def _auth_reject(e: firebase.AuthError) -> JSONResponse:
    """401 with token_expired when the ID token itself expired (client must
    refresh via Firebase), generic unauthorized otherwise."""
    code = "token_expired" if isinstance(e, firebase.TokenExpired) else "unauthorized"
    return JSONResponse({"error": code}, status_code=401)


# --------------------------------------------------------------------------- #
# middleware: request id + in-flight accounting + security/cache headers
# --------------------------------------------------------------------------- #
@app.middleware("http")
async def request_meta(request: Request, call_next):
    global _in_flight
    rid = uuid.uuid4().hex[:12]
    _in_flight += 1
    
    path = request.url.path
    method = request.method
    auth_header = request.headers.get("Authorization", "")
    token_preview = (auth_header[:35] + "...") if auth_header else "None"
    
    import sys
    print(f"\n[SERVER API LOG] 📥 INCOMING REQUEST: {method} {path} | Auth: {token_preview}", file=sys.stderr, flush=True)
    
    try:
        response = await call_next(request)
    finally:
        _in_flight -= 1
        
    print(f"[SERVER API LOG] 📤 OUTGOING RESPONSE: {method} {path} => Status: {response.status_code}\n", file=sys.stderr, flush=True)

    # ponytail: flush pending usage telemetry after every response so dev tracking
    # is live (prod flushes via aclose() per request; this is a no-op there since
    # the buffer is already empty). Upgrade path: interval flusher if D1 writes
    # ever need re-batching in prod.
    flusher = getattr(request.app.state, "flusher", None)
    if flusher is not None:
        try:
            await flusher.flush_now()
        except Exception:
            pass

    response.headers["X-Request-Id"] = rid
    response.headers["X-Inflight"] = str(_in_flight)
    # Security / anti-leak headers on every response
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["X-Content-Type-Options"] = "nosniff"
    # /signin is iframed by the extension's offscreen doc (Firebase popup auth
    # must run in an iframe per Google's extension-auth guide); rest stay DENY.
    if request.url.path != "/signin":
        response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# Never echo internals (tracebacks, full provider errors) to clients.
@app.exception_handler(Exception)
async def _unhandled_handler(_request: Request, _exc: Exception):
    return JSONResponse({"error": "internal_error"}, status_code=500)


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
@app.get("/healthz")
async def healthz():
    return {"ok": True}


_SIGNIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>VidRank sign-in</title>
</head>
<body>
<script src="https://www.gstatic.com/firebasejs/12.17.0/firebase-app.js"></script>
<script src="https://www.gstatic.com/firebasejs/12.17.0/firebase-auth.js"></script>
<script>
  firebase.initializeApp({
    apiKey: "AIzaSyAlRH6242b-yDFn5E9yfyIwof6LsL7nWp8",
    authDomain: "vidrank-5e540.firebaseapp.com",
    projectId: "vidrank-5e540"
  });
  const auth = firebase.auth();
  const post = (data) => window.parent.postMessage({source: "vidrank-signin", ...data}, "*");
  (async () => {
    try {
      const result = await auth.signInWithPopup(new firebase.auth.GoogleAuthProvider());
      const token = result.credential && result.credential.accessToken;
      const idToken = await result.user.getIdToken();
      post({ok: true, accessToken: token, idToken});
    } catch (e) {
      post({ok: false, error: (e && e.code) || "signin_failed"});
    }
  })();
</script>
</body>
</html>"""


@app.get("/signin", response_class=HTMLResponse)
async def signin():
    """Sign-in page iframed by the extension's offscreen doc; relays the Google
    OAuth access token back via postMessage (Firebase popup auth must run in an
    iframe served from outside the extension package — see Google's
    chrome-extension auth guide)."""
    return HTMLResponse(
        _SIGNIN_HTML,
        headers={"Content-Security-Policy": "frame-ancestors 'self' chrome-extension:"},
    )


@app.post("/v1/auth/login")
async def auth_login(request: Request):
    """Firebase auth + create/update user in D1.
    
    Extension sends Firebase ID token → Backend verifies → Returns session token
    """
    env = _bindings(request)
    auth_header = request.headers.get("Authorization", "")
    id_token = auth_header.removeprefix("Bearer ").strip()
    
    # Verify Firebase ID token
    try:
        claims = await firebase.verify_token(id_token, env)
    except firebase.AuthError as e:
        import sys; print(f"[auth-debug] /v1/auth rejected: {e}", file=sys.stderr, flush=True)
        return _auth_reject(e)
    
    uid = claims.get("uid", "")
    email = claims.get("email", "")
    name = claims.get("name", "")
    picture = claims.get("picture", "")
    
    # Get or create user in D1
    user = await db.get_user(env, uid)
    now = int(time.time())
    
    if not user:
        # First time login - create user
        user = {
            "firebase_uid": uid,
            "email": email,
            "tier": C.TIER_FREE,
            "is_active": 1,
            "synced_at": now,
            "usage_count": 0,
            "name": name or "",
            "photo_url": picture or ""
        }
        await db.upsert_user(env, user)
    else:
        # Update synced_at and user details
        user["synced_at"] = now
        if name: user["name"] = name
        if picture: user["photo_url"] = picture
        await db.upsert_user(env, user)
    
    # Get current quota status
    verdict = await quotas.get_quota(env, uid) or {}
    
    # Create backend session token (JWT)
    import jwt
    jwt_secret = getattr(env, "JWT_SECRET", "dev-jwt-secret")
    session_token = jwt.encode({
        "uid": uid,
        "email": email,
        "tier": user.get("tier", C.TIER_FREE),
        "iat": now,
        "exp": now + 7 * 24 * 3600  # 7 days
    }, jwt_secret, algorithm="HS256")
    
    return {
        "session_token": session_token,
        "user": {
            "uid": uid,
            "email": email,
            "name": user.get("name", ""),
            "photo_url": user.get("photo_url", ""),
            "tier": user.get("tier", C.TIER_FREE),
        },
        "quota": {
            "remaining": verdict.get("remaining", 0) if isinstance(verdict, dict) else 0,
            "limit": verdict.get("limit", C.DEFAULT_FREE_DAILY_LIMIT) if isinstance(verdict, dict) else C.DEFAULT_FREE_DAILY_LIMIT,
            "resets_in_seconds": verdict.get("resets_in_seconds", 0) if isinstance(verdict, dict) else 0
        }
    }


async def _chat_stream(request: Request, env, uid: str, model: str, messages: list[dict], 
                       temperature: float, max_tokens: int, body: dict):
    """Streaming chat endpoint with parallel chunk processing."""
    from starlette.responses import StreamingResponse
    
    # 1) Check quota first
    verdict = await quotas.get_quota(env, uid) or {"ok": True, "remaining": 10, "limit": 10, "resets_in_seconds": 0}
    if not verdict.get("ok"):
        return JSONResponse(
            {"error": "quota_exceeded",
             "quota_remaining": verdict.get("remaining", 0),
             "resets_in_seconds": verdict.get("resets_in_seconds", 0)},
            status_code=429,
        )
    
    # 2) Get user tier
    user = await db.get_user(env, uid)
    tier = (user or {}).get("tier") or C.TIER_FREE
    
    # 3) Check cache for full response (quick path)
    key = cache.exact_key(model, messages, temperature, max_tokens)
    cached = await cache.get_exact(env, key) if temperature == 0 else None
    if cached:
        async def cached_stream():
            yield f"data: {json.dumps({'content': cached, 'done': True, 'cache': 'HIT'})}\n\n"
        
        return StreamingResponse(
            cached_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Cache": "HIT"
            }
        )
    
    # 4) Chunk the messages for parallel processing
    message_chunks = chunking.chunk_messages(messages, max_chunks=5)
    
    async def stream_generator():
        """Generate SSE stream with chunked parallel processing."""
        try:
            if len(message_chunks) == 1:
                # Single request, no chunking needed - use standard path
                account = await router.pick_account(
                    env, 
                    time.strftime("%Y-%m-%d", time.gmtime()),
                    int(time.time()),
                    sticky_key=uid
                )
                
                if not account:
                    yield f"data: {json.dumps({'error': 'pool exhausted', 'done': True})}\n\n"
                    return
                
                result = await router.execute_request(
                    env,
                    user_id=uid,
                    account=account,
                    sticky_key=uid,
                    payload={
                        "model": model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens
                    }
                )
                
                content = result.get("content", "")
                
                # Log usage
                flusher = getattr(request.app.state, "flusher", None)
                if flusher:
                    flusher.log_usage(
                        user_id=uid,
                        account_id=result.get("account_id"),
                        model=model,
                        cache_hit=False,
                        latency_ms=result.get("latency_ms"),
                        status=result.get("status", 503),
                        ts=int(time.time())
                    )
                
                # Store in cache
                if result.get("status", 0) < 400 and content and temperature == 0:
                    await cache.store_exact(env, key, content)
                    if tier == C.TIER_FREE:
                        await cache.store_semantic(
                            env, uid, model, 
                            messages[-1].get("content", ""),
                            content
                        )
                
                # Stream single response
                yield f"data: {json.dumps({'content': content, 'done': True})}\n\n"
            
            else:
                # Multiple chunks - parallel processing
                # Send initial "processing" message
                yield f"data: {json.dumps({'content': '', 'processing': True, 'chunks': len(message_chunks)})}\n\n"
                
                # Process all chunks in parallel
                chunk_results = await chunking.process_chunks_parallel(
                    env,
                    message_chunks,
                    model,
                    temperature,
                    max_tokens,
                    uid
                )
                
                # Stream each chunk result as it completes
                for i, chunk_content in enumerate(chunk_results):
                    is_last = i == len(chunk_results) - 1
                    
                    if chunk_content:
                        yield f"data: {json.dumps({'content': chunk_content, 'chunk': i+1, 'done': is_last})}\n\n"
                
                # Merge and cache final result
                merged_content = chunking.merge_chunk_results(chunk_results, merge_strategy="list")
                
                if merged_content and temperature == 0:
                    await cache.store_exact(env, key, merged_content)
                    if tier == C.TIER_FREE:
                        await cache.store_semantic(
                            env, uid, model,
                            messages[-1].get("content", ""),
                            merged_content
                        )
                
                # Log usage for chunked request
                flusher = getattr(request.app.state, "flusher", None)
                if flusher:
                    flusher.log_usage(
                        user_id=uid,
                        account_id="chunked",
                        model=model,
                        cache_hit=False,
                        latency_ms=0,
                        status=200,
                        ts=int(time.time())
                    )
        
        except Exception as e:
            yield f"data: {json.dumps({'error': 'stream_error', 'done': True})}\n\n"
    
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/v1/chat")
async def chat(request: Request):
    env = _bindings(request)
    auth = request.headers.get("Authorization", "")
    token = auth.removeprefix("Bearer ").strip()
    try:
        claims = await firebase.verify_token(auth.removeprefix("Bearer ").strip(), env)
    except firebase.AuthError as e:
        import sys; print(f"[auth-debug] /v1/chat rejected: {e}", file=sys.stderr, flush=True)
        return _auth_reject(e)
    uid = claims.get("uid", "")

    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"error": "bad_request"}, status_code=400)
    model = body.get("model") or C.GROQ_MODEL
    messages = body.get("messages") or []
    stream = body.get("stream", False)  # NEW: streaming support
    if not isinstance(messages, list) or len(messages) > C.MAX_MESSAGES:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    temperature = body.get("temperature", 0.7)
    max_tokens = body.get("max_tokens", 1024)
    if not isinstance(max_tokens, int) or not (1 <= max_tokens <= C.MAX_TOKENS):
        return JSONResponse({"error": "bad_request"}, status_code=400)
    
    # NEW: If streaming requested, use streaming endpoint
    if stream:
        return await _chat_stream(request, env, uid, model, messages, temperature, max_tokens, body)

    # 1) exact cache (Layer 3) — hit skips provider AND quota
    key = cache.exact_key(model, messages, temperature, max_tokens)
    cached = await cache.get_exact(env, key) if temperature == 0 else None
    if cached:
        return JSONResponse(
            {"content": cached, "model": model, "cache": "HIT"},
            headers={"X-Cache": "HIT"},
        )

    # 2) quota check (free: dailyLimit; pro: unlimited)
    verdict = await quotas.get_quota(env, uid) or {"ok": True, "remaining": 10, "limit": 10, "resets_in_seconds": 0}
    if not verdict.get("ok"):
        return JSONResponse(
            {"error": "quota_exceeded",
             "quota_remaining": verdict.get("remaining", 0),
             "resets_in_seconds": verdict.get("resets_in_seconds", 0)},
            status_code=429,
        )

    # 3) semantic cache (Layer 1, free users)
    user = await db.get_user(env, uid)
    tier = (user or {}).get("tier") or C.TIER_FREE
    if tier == C.TIER_FREE:
        sem = await cache.get_semantic(env, uid, model, messages[-1].get("content", ""))
        if sem:
            return JSONResponse({"content": sem, "model": model, "cache": "SEM"},
                                headers={"X-Cache": "SEM"})

    # 4) burst smoothing: in-flight cap => queue (both free and pro)
    if _in_flight > C.IN_FLIGHT_CAP:
        if tier == C.TIER_FREE:
            await mq.enqueue_free(env, {"user_id": uid, "body": body, "model": model})
            return JSONResponse(
                {"error": "queued", "message": "burst: request queued"},
                status_code=202, headers={"Retry-After": "600"},
            )
        else:  # PRO: also queue but with faster retry
            await mq.enqueue_pro(env, {"user_id": uid, "body": body, "model": model})
            return JSONResponse(
                {"error": "queued", "message": "high load: request queued for priority processing"},
                status_code=202, headers={"Retry-After": "10"},
            )

    # 5) route to the pool (with fallback inside router)
    account = await router.pick_account(env, time.strftime("%Y-%m-%d", time.gmtime()),
                                        int(time.time()), sticky_key=uid)
    if not account:
        return JSONResponse({"error": "provider pool exhausted"}, status_code=503,
                            headers={"Retry-After": "60"})

    result = await router.execute_request(env, user_id=uid, account=account, sticky_key=uid,
                                          payload={"model": model, "messages": messages,
                                                   "temperature": temperature,
                                                   "max_tokens": max_tokens})

    # 6) log usage (batched flusher) + store caches on success
    flusher = getattr(request.app.state, "flusher", None)
    if flusher is not None:
        flusher.log_usage(
            user_id=uid, account_id=result.get("account_id"), model=model,
            cache_hit=result.get("cache_hit", False),
            latency_ms=result.get("latency_ms"), status=result.get("status", 503),
            ts=int(time.time()),
        )
    if result.get("status", 0) < 400 and result.get("content"):
        if temperature == 0:
            await cache.store_exact(env, key, result["content"])
        if tier == C.TIER_FREE:
            await cache.store_semantic(env, uid, model, messages[-1].get("content", ""),
                                       result["content"])

    return JSONResponse(
        # Deliberately omit account_id — reveals internal pool topology.
        {"content": result.get("content", ""), "model": model, "cache": "MISS"},
        status_code=result.get("status", 503),
        headers={"Retry-After": "60"} if result.get("status", 503) >= 500 else {},
    )


@app.post("/v1/generate")
async def generate(request: Request):
    env = _bindings(request)
    auth = request.headers.get("Authorization", "")
    try:
        claims = await firebase.verify_token(auth.removeprefix("Bearer ").strip(), env)
    except firebase.AuthError as e:
        import sys; print(f"[auth-debug] /v1/generate rejected: {e}", file=sys.stderr, flush=True)
        return _auth_reject(e)
    uid = claims.get("uid", "")

    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    title = body.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 2000:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    description = body.get("description") or ""
    if not isinstance(description, str) or len(description) > 5000:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    title, description = title.strip(), description.strip()

    user = await db.get_user(env, uid)
    tier = (user or {}).get("tier") or C.TIER_FREE

    messages = [
        {"role": "system", "content": prompts.GENERATE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Title: {title}\nDescription: {description or 'None'}"},
    ]

    # 1) exact cache (Layer 3) — hit skips provider AND quota
    key = cache.exact_key(prompts.GENERATE_MODEL, messages, 0.0, 1024)
    cached = await cache.get_exact(env, key)
    if cached:
        try:
            data = json.loads(cached)
            tags, desc = data.get("tags") or [], data.get("description") or ""
        except (ValueError, TypeError):
            tags, desc = [], ""
        if tags and desc:
            # ponytail: log cache-hits too so telemetry reflects real served
            # volume (no provider credit consumed, but visible in /v1/history).
            flusher = getattr(request.app.state, "flusher", None)
            if flusher is not None:
                flusher.log_usage(
                    user_id=uid, account_id=None, model=prompts.GENERATE_MODEL,
                    cache_hit=True, latency_ms=0, status=200, ts=int(time.time()),
                )
            usage, retry_after = await _usage_for(env, uid, tier)
            return JSONResponse(
                {"success": True, "tags": tags, "description": desc,
                 "usage": usage, "retry_after": retry_after},
                headers={"X-Cache": "HIT"},
            )

    # 2) quota check (free: dailyLimit; pro: unlimited)
    verdict = await quotas.get_quota(env, uid) or {"ok": True, "remaining": 10, "limit": 10, "resets_in_seconds": 0}
    if not verdict.get("ok"):
        return JSONResponse(
            {"error": "quota_exceeded",
             "quota_remaining": verdict.get("remaining", 0),
             "resets_in_seconds": verdict.get("resets_in_seconds", 0)},
            status_code=429,
        )

    # 3) route to the pool (with fallback inside router)
    account = await router.pick_account(env, time.strftime("%Y-%m-%d", time.gmtime()),
                                        int(time.time()), sticky_key=title)
    if not account:
        return JSONResponse({"error": "provider pool exhausted"}, status_code=503,
                            headers={"Retry-After": "60"})

    result = await router.execute_request(
        env, user_id=uid, account=account, sticky_key=title,
        payload={"model": prompts.GENERATE_MODEL, "messages": messages,
                 "temperature": 0.0, "max_tokens": 1024},
    )

    # 4) log usage (batched flusher)
    flusher = getattr(request.app.state, "flusher", None)
    if flusher is not None:
        flusher.log_usage(
            user_id=uid, account_id=result.get("account_id"), model=prompts.GENERATE_MODEL,
            cache_hit=result.get("cache_hit", False),
            latency_ms=result.get("latency_ms"), status=result.get("status", 503),
            ts=int(time.time()),
        )

    if result.get("status", 0) >= 400 or not result.get("content"):
        status = result.get("status", 503)
        return JSONResponse(
            {"error": "generation_failed"},
            status_code=status,
            headers={"Retry-After": "60"} if status >= 500 else {},
        )

    parsed = _parse_generate(result.get("content", ""))
    if not parsed:
        return JSONResponse({"error": "generation_failed"}, status_code=502)

    # 5) consume quota only after a successful generation
    await _consume_quota(env, uid)

    tags, desc = parsed["tags"], parsed["description"]
    await cache.store_exact(env, key, json.dumps({"tags": tags, "description": desc}))

    usage, retry_after = await _usage_for(env, uid, tier)
    return JSONResponse(
        {"success": True, "tags": tags, "description": desc,
         "usage": usage, "retry_after": retry_after},
    )


def _parse_generate(content: str) -> dict | None:
    """Extract {tags, description} from the LLM's JSON output (may include fences).

    LLMs routinely emit raw control characters (literal newlines) inside JSON
    string values, which strict json.loads rejects. Scrub them before parsing.
    """
    text = content.strip()
    if text.startswith("```"):
        first = text.find("\n")
        last = text.rfind("```")
        if first != -1 and last != -1:
            text = text[first + 1:last].strip()
    text = _scrub_json_control_chars(text)
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    tags = data.get("tags")
    desc = data.get("description")
    if not isinstance(tags, list) or not isinstance(desc, str):
        return None
    return {"tags": _clean_tags(tags), "description": desc.strip()}


def _scrub_json_control_chars(text: str) -> str:
    """Replace raw C0 control chars (\\x00-\\x1f) with a space. Already-escaped
    sequences like `\\n` in the text are the two characters backslash+n and are
    NOT matched, so valid escapes survive untouched."""
    return re.sub(r"[\x00-\x1f]", " ", text)


def _clean_tags(tags: list) -> list[str]:
    """Backend cleaning: strip whitespace/leading '#', dedupe, cap at 20."""
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        s = str(t).strip().lstrip("#").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[: prompts.MAX_GENERATE_TAGS]


async def _consume_quota(env, uid: str) -> None:
    """Inc the user's QuotaDO after a successful generation (pro: no-op)."""
    try:
        do = env.QUOTA.get(uid)
        if do is not None:
            await do.inc()
    except Exception:
        pass  # race over limit or DO unavailable: usage read stays authoritative


async def _usage_for(env, uid: str, tier: str) -> tuple[dict, int]:
    """(usage, retry_after) from live DO verdict; retry_after per DELAYS curve."""
    verdict = {}
    try:
        verdict = await quotas.get_quota(env, uid) or {}
    except Exception:
        verdict = {}
    limit, remaining = (verdict.get("limit") if isinstance(verdict, dict) else None), (verdict.get("remaining") if isinstance(verdict, dict) else None)
    if limit is None or remaining is None or remaining < 0:
        return {"used": -1, "limit": -1, "plan": tier}, 0  # pro / DO down
    used = max(0, limit - remaining)
    if tier == C.TIER_PRO:
        return {"used": used, "limit": -1, "plan": tier}, 0
    idx = min(max(used - 1, 0), len(C.GENERATE_DELAYS) - 1)
    return {"used": used, "limit": limit, "plan": tier}, C.GENERATE_DELAYS[idx]


@app.get("/v1/me")
async def me(request: Request):
    env = _bindings(request)
    auth = request.headers.get("Authorization", "")
    try:
        claims = await firebase.verify_token(auth.removeprefix("Bearer ").strip(), env)
    except firebase.AuthError as e:
        return _auth_reject(e)
    uid = claims.get("uid", "")
    user = await db.get_user(env, uid)
    tier = (user or {}).get("tier") or C.TIER_FREE
    verdict = await quotas.get_quota(env, uid) or {}
    return {
        "uid": uid,
        "email": claims.get("email") or (user or {}).get("email"),
        "tier": tier,
        "quota_remaining": verdict.get("remaining", -1) if isinstance(verdict, dict) else -1,
        "quota_limit": verdict.get("limit") if isinstance(verdict, dict) else C.DEFAULT_FREE_DAILY_LIMIT,
        "resets_in_seconds": verdict.get("resets_in_seconds", 0),
    }


@app.get("/v1/history")
async def history(request: Request, limit: int = 50):
    env = _bindings(request)
    try:
        claims = await firebase.verify_token(
            request.headers.get("Authorization", "").removeprefix("Bearer ").strip(), env)
    except firebase.AuthError as e:
        return _auth_reject(e)
    uid = claims.get("uid", "")
    rows = await db._fetch_all(
        env,
        "SELECT model, cache_hit, latency_ms, status, ts FROM usage_log "
        "WHERE user_id=?1 ORDER BY ts DESC LIMIT ?2",
        uid, min(max(limit, 1), 200),
    )
    return {"items": rows}


@app.post("/v1/auth/sync")
async def auth_sync(request: Request):
    """Webhook: chrome extension calls on login with the Firebase ID token.

    Verifies the token, then syncs that one user's Firestore doc into D1
    (tier, usage, subscription). No-op cleanly when Firestore or D1 is absent,
    so local/dev requests degrade gracefully instead of erroring.
    """
    env = _bindings(request)
    try:
        claims = await firebase.verify_token(
            request.headers.get("Authorization", "").removeprefix("Bearer ").strip(), env)
    except firebase.AuthError as e:
        return _auth_reject(e)
    uid = claims.get("uid", "")
    synced = await sync.sync_one_user(env, uid)
    # Fall back to a minimal row so quota/tier work even without Firestore.
    if not synced:
        await db.upsert_user(env, {
            "firebase_uid": uid,
            "email": claims.get("email", ""),
            "tier": C.TIER_FREE,
            "is_active": 1,
            "synced_at": int(time.time()),
        })
    user = await db.get_user(env, uid)
    return {"synced": bool(synced), "uid": uid, "tier": (user or {}).get("tier") or C.TIER_FREE}


# --------------------------------------------------------------------------- #
# admin API
# --------------------------------------------------------------------------- #
@app.post("/admin/login")
async def admin_login(request: Request):
    """Password login. Returns an admin session token (expires 8h)."""
    env = _bindings(request)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    if not admin_mod.check_admin_password(env, str(body.get("password", ""))):
        return JSONResponse({"error": "invalid_credentials"}, status_code=401)
    return {"token": admin_mod.issue_token(env), "expires_in_s": admin_mod.ADMIN_SESSION_TTL_S}


async def _admin(request: Request) -> str | None:
    env = _bindings(request)
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return "admin" if admin_mod.verify_token(env, token) else None


@app.get("/admin/accounts")
async def admin_list_accounts(request: Request):
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return {"accounts": await db.list_enabled_accounts(env)}


@app.get("/admin/accounts/all")
async def admin_list_all_accounts(request: Request):
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return {"accounts": await db.list_accounts(env)}


@app.get("/admin/accounts/usage")
async def admin_accounts_usage(request: Request, days: int = 7):
    """Per-account rollup chart data: usage vs limit, up to `days` back."""
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    days = min(max(days, 1), 90)
    accounts = await db.list_accounts(env)
    out = []
    for a in accounts:
        rollups = await db.get_account_usage_days(env, a["id"], days)
        out.append({
            "id": a["id"],
            "provider": a["provider"],
            "label": a["label"],
            "daily_limit": a["daily_limit"],
            "rpm_limit": a["rpm_limit"],
            "enabled": a["enabled"],
            "days": rollups,
        })
    return {"accounts": out}


@app.post("/admin/accounts")
async def admin_add_account(request: Request):
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    provider = body.get("provider", "")
    if provider not in ("groq", "openrouter"):
        return JSONResponse({"error": "provider must be groq|openrouter"}, status_code=400)
    if not body.get("key"):
        return JSONResponse({"error": "key required"}, status_code=400)
    account_id = uuid.uuid4().hex[:16]
    defaults = C.PROVIDER_DEFAULTS.get(provider, {"daily_limit": 100, "rpm_limit": 20})
    await db.add_account(env, {
        "id": account_id,
        "provider": provider,
        "label": body.get("label"),
        "key_enc": admin_mod.encrypt_key(env, body["key"]),
        "daily_limit": int(body.get("daily_limit") or defaults["daily_limit"]),
        "rpm_limit": int(body.get("rpm_limit") or defaults["rpm_limit"]),
        "enabled": 1,
        "created_at": int(time.time()),
    })
    return {"account_id": account_id}


@app.put("/admin/accounts/{account_id}")
async def admin_update_account(request: Request, account_id: str):
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    existing = await db.get_account(env, account_id)
    if not existing:
        return JSONResponse({"error": "not found"}, status_code=404)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    fields = {}
    if body.get("label") is not None:
        fields["label"] = str(body["label"])
    for key in ("daily_limit", "rpm_limit", "enabled"):
        if body.get(key) is not None:
            fields[key] = int(body[key])
    await db.update_account(env, account_id, fields)
    return {"account_id": account_id, "updated": list(fields.keys())}


@app.delete("/admin/accounts/{account_id}")
async def admin_delete_account(request: Request, account_id: str):
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    existing = await db.get_account(env, account_id)
    if not existing:
        return JSONResponse({"error": "not found"}, status_code=404)
    await db.delete_account(env, account_id)
    return {"deleted": account_id}


@app.get("/admin/accounts/health")
async def admin_accounts_health(request: Request):
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    out = {}
    for a in await db.list_enabled_accounts(env):
        try:
            out[a["id"]] = await env.RATESTATE.get(a["id"]).get_health()
        except Exception:
            out[a["id"]] = {"health": None}
    return {"health": out}


@app.get("/admin/accounts/{account_id}/usage")
async def admin_account_usage(request: Request, account_id: str):
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        live = await env.RATESTATE.get(account_id).get_live()
        acc = await db.get_account(env, account_id)
        return {"live": live, "limit": (acc or {}).get("daily_limit"),
                "rpm_limit": (acc or {}).get("rpm_limit")}
    except Exception:
        return JSONResponse({"error": "not found"}, status_code=404)


@app.get("/admin/stats/overview")
async def admin_stats_overview(request: Request):
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    rows = await db._fetch_all(
        env, "SELECT * FROM usage_daily ORDER BY day DESC LIMIT 7")
    return {"days": rows}


@app.get("/admin/stats/usage")
async def admin_stats_usage(request: Request, days: int = 7):
    """Site-wide rollup chart (usage_daily), up to `days` back."""
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    days = min(max(days, 1), 90)
    return {"days": await db.get_usage_days(env, days)}


@app.get("/admin/users")
async def admin_list_users(request: Request, tier: str | None = None):
    """List all users (optionally filtered by tier). Mirrors Firestore users."""
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return {"users": await db.list_users(env, tier)}


@app.patch("/admin/users/{uid}")
async def admin_set_user_tier(request: Request, uid: str):
    """Set a user's tier (e.g. upgrade to pro). Writes Firestore, then D1."""
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    tier = (body.get("tier") or "").strip().lower()
    if tier not in ("free", "pro"):
        return JSONResponse({"error": "tier must be free|pro"}, status_code=400)
    try:
        await sync.set_user_tier(env, uid, tier)
    except Exception:
        pass  # Firestore unreachable in local dev; D1 write below still applies
    await db.set_user_tier(env, uid, tier)
    return {"uid": uid, "tier": tier}


@app.get("/admin/plans")
async def admin_list_plans(request: Request):
    """List plan docs. Mirrors Firestore plan collection."""
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    rows = await db._fetch_all(
        env, "SELECT plan_id, daily_limit, price, plandetails FROM plans")
    return {"plans": rows}


@app.get("/admin/pricing")
async def admin_get_pricing(request: Request):
    """Get dynamic pricing configuration from plans."""
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    
    plans = await db._fetch_all(
        env, "SELECT plan_id, price, daily_limit FROM plans")
    
    # Format for dashboard consumption
    pricing = {}
    for plan in plans:
        plan_id = plan.get('plan_id', '')
        pricing[plan_id] = {
            'monthly_price': float(plan.get('price') or 0),
            'daily_limit': plan.get('daily_limit'),
            # Estimate cost per request (pro users get cheaper rate)
            'request_cost': 0.0001 if plan_id == 'free' else 0.00008
        }
    
    return {"pricing": pricing}


@app.patch("/admin/plans")
async def admin_update_plan(request: Request):
    """Update a plan (set free plan's daily_limit). Writes Firestore, then D1."""
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    plan_id = (body.get("plan_id") or "").strip()
    if plan_id not in ("free", "pro"):
        return JSONResponse({"error": "plan_id must be free|pro"}, status_code=400)
    daily_limit = body.get("daily_limit")
    if daily_limit is not None:
        daily_limit = int(daily_limit)
        try:
            await sync.update_plan_limit(env, plan_id, daily_limit)
        except Exception:
            pass  # Firestore unreachable locally; D1 write below still applies
        await env.DB.prepare(
            "UPDATE plans SET daily_limit=?1 WHERE plan_id=?2"
        ).bind(daily_limit, plan_id).run()
    return {"plan_id": plan_id, "daily_limit": daily_limit}


# --------------------------------------------------------------------------- #
# Cloudflare Worker entrypoint (wrangler main = app/main.py)
# --------------------------------------------------------------------------- #
def create_asgi_bridge():
    """Worker -> ASGI bridge: attach env to app.state, then dispatch via asgi.fetch."""
    from cloudflare import asgi  # type: ignore  (workers-py)
    from cloudflare.workers import WorkerEntrypoint  # type: ignore

    class VRRouterEntrypoint(WorkerEntrypoint):
        async def fetch(self, request):
            app.state.env = self.env
            app.state.flusher = db.BatchedFlusher(self.env)
            resp = await asgi.fetch(request, app)
            await app.state.flusher.aclose()
            return resp

    return VRRouterEntrypoint


try:
    VRRouterEntrypoint = create_asgi_bridge()
except Exception:
    # local dev without workers-py: FastAPI runnable standalone
    @app.on_event("startup")
    async def _startup():
        pass
    VRRouterEntrypoint = None