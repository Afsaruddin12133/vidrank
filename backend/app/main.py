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

import asyncio
import json
import os
import re
import sys
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

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
# ALLOWED_ORIGINS is a CSV Cloudflare var, but Python Workers expose vars via
# self.env (app.state.env), NOT os.environ — so resolve lazily per request.
_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
_ALLOW_HEADERS = ["Authorization", "Content-Type", "Cookie"]


def _allowed_origins() -> list[str]:
    """Resolve CSV ALLOWED_ORIGINS from worker env, falling back to os.environ (local dev)."""
    env = getattr(app.state, "env", None)
    raw = ""
    if env is not None:
        raw = getattr(env, "ALLOWED_ORIGINS", "") or ""
    if not raw:
        raw = os.environ.get("ALLOWED_ORIGINS", "") or ""
    return [o.strip() for o in raw.split(",") if o.strip()]


class _CORS:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        origin = next(
            (v.decode() for k, v in scope.get("headers", []) if k == b"origin"), None
        )
        allowed = origin in _allowed_origins()

        async def send_wrapper(message):
            if message["type"] == "http.response.start" and allowed:
                headers = list(message.get("headers", []))
                headers.append((b"access-control-allow-origin", origin.encode()))
                headers.append((b"access-control-allow-credentials", b"true"))
                headers.append((b"vary", b"Origin"))
                headers.append((b"access-control-expose-headers", b"X-Request-Id"))
                message["headers"] = headers
            await send(message)

        if allowed and origin is not None:
            method = next(
                (v.decode() for k, v in scope.get("headers", []) if k == b"access-control-request-method"),
                None,
            )
            if method is not None:
                headers = [
                    (b"access-control-allow-origin", origin.encode()),
                    (b"access-control-allow-credentials", b"true"),
                    (b"vary", b"Origin"),
                    (b"access-control-allow-methods", ", ".join(_ALLOW_METHODS).encode()),
                    (b"access-control-allow-headers", ", ".join(_ALLOW_HEADERS).encode()),
                    (b"access-control-max-age", b"86400"),
                ]
                response_start = {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": headers,
                }
                await send(response_start)
                await send({"type": "http.response.body", "body": b"", "more_body": False})
                return
        return await self.app(scope, receive, send_wrapper)


app.add_middleware(_CORS)

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
    if isinstance(e, firebase.TokenExpired):
        return JSONResponse({"error": "token_expired"}, status_code=401)
    if "not verified" in str(e):
        return JSONResponse(
            {"error": "email_not_verified",
             "message": "Please verify your email address, then try again."},
            status_code=403)
    return JSONResponse({"error": "unauthorized"}, status_code=401)


# --------------------------------------------------------------------------- #
# middleware: request id + in-flight accounting + security/cache headers.
# NOTE: pure ASGI, NOT BaseHTTPMiddleware — BaseHTTPMiddleware re-buffers the
# response via a collapsing task group and HANGS on python_workers with
# StreamingResponse (SSE chat) -> runtime cancels -> 500.
# --------------------------------------------------------------------------- #
class MIT_RequestMeta:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        global _in_flight
        rid = uuid.uuid4().hex[:12]
        _in_flight += 1
        t_start = time.time()

        path = scope.get("path", "?")
        method = scope.get("method", "?")
        auth = ""
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                auth = value.decode("latin1", "replace")
        token_preview = (auth[:35] + "...") if auth else "None"

        import sys
        print(f"\n[SERVER] INCOMING REQUEST: {method} {path} | Auth: {token_preview}", file=sys.stderr, flush=True)

        # IP-derived geo telemetry from Cloudflare `cf` — captured PER REQUEST,
        # so a user's location changes are reflected in every API call.
        cf = scope.get("cf") or {}
        flusher = getattr(getattr(scope.get("app"), "state", None), "flusher", None)
        if flusher is not None:
            flusher.geo = (cf.get("country"), cf.get("region"), cf.get("city"))

        logged = []
        def send_wrapper(message):
            if message["type"] == "http.response.start":
                logged.append(1)
                print(f"[SERVER MIDDLEWARE] OUTGOING RESPONSE: {method} {path} => Status: {message['status']} | {int((time.time() - t_start) * 1000)}ms\n", file=sys.stderr, flush=True)
                message.setdefault("headers", []).extend([
                    (b"x-request-id", rid.encode()),
                    (b"x-inflight", str(_in_flight).encode()),
                    (b"cache-control", b"no-store, no-cache, must-revalidate"),
                    (b"pragma", b"no-cache"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                ])
                # /signin is iframed by the extension's offscreen doc (Firebase
                # popup auth must run in an iframe per Google's extension-auth
                # guide); rest stay DENY.
                if path != "/signin":
                    message["headers"].append((b"x-frame-options", b"DENY"))
            return send(message)

        try:
            await self.app(scope, receive, send_wrapper)
            if flusher is not None:
                try:
                    await flusher.flush_now()
                except Exception:
                    pass
        finally:
            _in_flight -= 1


app.add_middleware(MIT_RequestMeta)


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
    
    # Create backend session token (JWT) — stdlib HS256 via admin module (PyJWT not bundled)
    session_token = admin_mod.issue_user_token(env, uid, email, user.get("tier", C.TIER_FREE))

    billing_price_id = None
    sub_id = user.get("subscription_id")
    if user.get("tier", C.TIER_FREE) == C.TIER_PRO and sub_id:
        try:
            sub = await db.get_subscription_by_id(env, sub_id)
            billing_price_id = (sub or {}).get("price_id")
        except Exception:
            pass

    return {
        "session_token": session_token,
        "user": {
            "uid": uid,
            "email": email,
            "name": user.get("name", ""),
            "photo_url": user.get("photo_url", ""),
            "tier": user.get("tier", C.TIER_FREE),
            "billing_price_id": billing_price_id,
        },
        "quota": {
            "remaining": (verdict.get("remaining") if isinstance(verdict, dict) and isinstance(verdict.get("remaining"), int) and verdict.get("remaining") >= 0 else (C.DEFAULT_FREE_DAILY_LIMIT if user.get("tier", C.TIER_FREE) != C.TIER_PRO else -1)),
            "limit": (verdict.get("limit") if isinstance(verdict, dict) and isinstance(verdict.get("limit"), int) and verdict.get("limit") >= 0 else (C.DEFAULT_FREE_DAILY_LIMIT if user.get("tier", C.TIER_FREE) != C.TIER_PRO else -1)),
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
                        error_msg=result.get("error_msg"),
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
    model = body.get("model") or C.DEFAULT_MODEL
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


@app.get("/v1/_debug_fetch")
async def debug_fetch(request: Request):
    try:
        from js import fetch as js_fetch
        resp = await js_fetch("https://openrouter.ai/api/v1/chat/completions", {"method": "POST"})
        status = resp.status
        body = (await resp.text())[:200]
        return {"js_fetch": "ok", "status": status, "body": body}
    except Exception as e:
        return {"js_fetch": "error", "type": type(e).__name__, "msg": str(e)[:300]}


@app.post("/v1/_debug_stages")
async def debug_stages(request: Request):
    env = _bindings(request)
    markers = []

    async def mark(stage: str):
        try:
            await env.DB.prepare(
                "INSERT INTO debug_log (stage, ts) VALUES (?1, ?2)"
            ).bind(stage, int(time.time())).run()
        except Exception:
            pass
        markers.append(stage)

    await mark("start")
    body = await _read_json(request)
    await mark("body_read")
    auth = request.headers.get("Authorization", "")
    try:
        claims = await firebase.verify_token(auth.removeprefix("Bearer ").strip(), env)
        await mark("auth_ok")
    except Exception as e:
        await mark("auth_fail")
        return {"markers": markers, "auth_error": str(e)[:200]}
    uid = claims.get("uid", "")
    user = await db.get_user(env, uid)
    await mark("user_lookup")
    try:
        verdict = await quotas.get_quota(env, uid)
        await mark("quota_ok")
    except Exception as e:
        await mark("quota_fail")
        return {"markers": markers, "quota_error": f"{type(e).__name__}: {e}"[:300]}
    try:
        account = await router.pick_account(env, time.strftime("%Y-%m-%d", time.gmtime()),
                                            int(time.time()), sticky_key="debug-stage")
        await mark(f"pick_account:{'ok' if account else 'empty'}")
    except Exception as e:
        await mark("pick_fail")
        return {"markers": markers, "pick_error": f"{type(e).__name__}: {e}"[:300]}
    if not account:
        return {"markers": markers, "account": None}
    key = router._decode_key(env, account)
    await mark(f"decrypt:{len(key)}")

    # test KV binding (cache.get_exact)
    try:
        keyx = cache.exact_key(prompts.GENERATE_MODEL, [{"role": "system", "content": "x"}], 0.0, 1024)
        cached = await cache.get_exact(env, keyx)
        await mark(f"kv_get:{cached is not None}")
    except Exception as e:
        await mark(f"kv_fail")
        return {"markers": markers, "kv_error": f"{type(e).__name__}: {e}"[:300]}

    # test js_fetch provider post sub-steps (find which line kills the isolate)
    from js import fetch as js_fetch
    url = router.ENDPOINTS.get(account.get("provider", ""))
    payload = {"model": prompts.GENERATE_MODEL, "messages": [{"role": "system", "content": "hi"}],
               "temperature": 0.0, "max_tokens": 16}
    try:
        await mark("pp1_noconfig")
        r0 = await js_fetch("https://openrouter.ai/api/v1/chat/completions", {"method": "POST"})
        await mark("pp2_bare_ok")
    except Exception as e:
        return {"markers": markers, "pp2_error": f"{type(e).__name__}: {e}"[:300]}
    try:
        from js import JSON as js_JSON
        init1 = js_JSON.parse('{"method":"POST","headers":{"Content-Type":"application/json"}}')
        r1 = await js_fetch(url, init1)
        await mark("pp4_headers_ok")
    except Exception as e:
        return {"markers": markers, "pp4_error": f"{type(e).__name__}: {e}"[:300]}
    try:
        init2 = js_JSON.parse('{"method":"POST","headers":{"Content-Type":"application/json"},"body":"{}"}')
        r2 = await js_fetch(url, init2)
        await mark("pp6_body_ok")
    except Exception as e:
        return {"markers": markers, "pp6_error": f"{type(e).__name__}: {e}"[:300]}
    try:
        t = await r2.text()
        await mark("pp8_text_ok")
    except Exception as e:
        return {"markers": markers, "pp8_error": f"{type(e).__name__}: {e}"[:300]}
    enc_rt = admin_mod.encrypt_key(env, "rt-test-key-123")
    dec_rt = admin_mod.decrypt_key(env, enc_rt)
    dec_seed = admin_mod.decrypt_key(env, account["key_enc"])
    return {"markers": markers, "done": True, "final_text_len": len(t),
            "roundtrip": dec_rt == "rt-test-key-123", "dec_seed_len": len(dec_seed)}


@app.post("/v1/generate")
async def generate(request: Request):
    try:
        return await _generate_impl(request)
    except Exception as e:
        import traceback
        return JSONResponse({"error": "internal", "type": type(e).__name__, "msg": str(e)[:500], "tb": traceback.format_exc()[-1500:]}, status_code=500)


async def _generate_impl(request: Request):
    env = _bindings(request)
    auth = request.headers.get("Authorization", "")
    t0 = time.time()
    try:
        claims = await firebase.verify_token(auth.removeprefix("Bearer ").strip(), env)
    except firebase.AuthError as e:
        print(f"[auth-debug] /v1/generate rejected: {e}", file=sys.stderr, flush=True)
        return _auth_reject(e)
    uid = claims.get("uid", "")
    print(f"[generate] t={time.time() - t0:.2f}s auth ok uid={uid[:10]}", file=sys.stderr, flush=True)

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
    if user and user.get("is_active") == 0:
        return JSONResponse(
            {"error": "account_suspended", "message": "Account suspended by administrator"},
            status_code=403,
        )
    tier = db.get_effective_tier(user) if user else C.TIER_FREE

    messages = [
        {"role": "system", "content": prompts.GENERATE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Title: {title}\nDescription: {description or 'None'}\n\n[Note: Strictly generate tags and description for the topic of '{title}'. If the description discusses an unrelated topic, ignore it completely.]"},
    ]

    # 1) exact cache (Layer 3) — hit skips provider AND quota
    # Cache key uses NORMALIZED text so "How To Grow!" and "how to grow"
    # share one global entry; the provider request itself stays verbatim.
    norm_messages = [
        {"role": "system", "content": messages[0]["content"]},
        {"role": "user", "content": f"Title: {cache.norm_text(title)}\nDescription: {cache.norm_text(description or '')}"},
    ]
    key = cache.exact_key(prompts.GENERATE_MODEL, norm_messages, 0.0, 1024)
    cached = await cache.get_exact(env, key)
    if cached:
        try:
            data = json.loads(cached)
            tags, desc = data.get("tags") or [], data.get("description") or ""
        except (ValueError, TypeError):
            tags, desc = [], ""
            if tags and desc:
                print(f"[generate] t={time.time() - t0:.2f}s cache HIT(exact) uid={uid[:10]}", file=sys.stderr, flush=True)
                flusher = getattr(request.app.state, "flusher", None)
                if flusher is not None:
                    flusher.log_usage(
                        user_id=uid, account_id=None, model=prompts.GENERATE_MODEL,
                        cache_hit=True, latency_ms=0, status=200, ts=int(time.time()),
                    )
                await _consume_quota(env, uid)
                usage, retry_after = await _usage_for(env, uid, tier)
                return JSONResponse(
                    {"success": True, "tags": tags, "description": desc,
                     "usage": usage, "retry_after": retry_after},
                    headers={"X-Cache": "HIT"},
                )

    # 2) semantic cache (near-repeat titles) — hit skips quota + provider,
    #    so repeat-y usage stays within the free daily cap and costs $0.
    if C.TIER_FREE == tier:
        sem_key_text = f"{title}\n{description or 'None'}"
        sem = await cache.get_semantic(env, uid, prompts.GENERATE_MODEL, sem_key_text)
        if sem:
            try:
                data = json.loads(sem)
                tags, desc = data.get("tags") or [], data.get("description") or ""
            except (ValueError, TypeError):
                tags, desc = [], ""
            if tags and desc:
                print(f"[generate] t={time.time() - t0:.2f}s cache HIT(semantic) uid={uid[:10]}", file=sys.stderr, flush=True)
                flusher = getattr(request.app.state, "flusher", None)
                if flusher is not None:
                    flusher.log_usage(
                        user_id=uid, account_id=None, model=prompts.GENERATE_MODEL,
                        cache_hit=True, latency_ms=0, status=200, ts=int(time.time()),
                    )
                await _consume_quota(env, uid)
                usage, retry_after = await _usage_for(env, uid, tier)
                return JSONResponse(
                    {"success": True, "tags": tags, "description": desc,
                     "usage": usage, "retry_after": retry_after},
                    headers={"X-Cache": "SEM"},
                )

    # 3) quota check (free: dailyLimit; pro: unlimited) + spam guard
    if tier != C.TIER_PRO:
        u_dict, _ = await _usage_for(env, uid, tier)
        if u_dict.get("remaining", 1) <= 0:
            resets = max(0, int(((int(time.time()) // 86400) + 1) * 86400 - time.time()))
            print(f"[generate] t={time.time() - t0:.2f}s quota_exceeded uid={uid[:10]}", file=sys.stderr, flush=True)
            return JSONResponse(
                {"error": "quota_exceeded",
                 "quota_remaining": 0,
                 "resets_in_seconds": resets},
                status_code=429,
            )
    print(f"[generate] t={time.time() - t0:.2f}s quota ok, routing to pool", file=sys.stderr, flush=True)

    # Sliding-window spam guard BEFORE touching the provider pool: rapid
    # button-spam burns OpenRouter RPM for nothing. Read-only DO check —
    # the post-success _consume_quota (inc) owns the real counts.
    try:
        guard = await env.QUOTA.get(env.QUOTA.idFromName(uid)).spam_check()
    except Exception:
        guard = {"ok": True}
    if isinstance(guard, dict) and guard.get("rate_limited"):
        wait = int(guard.get("retry_after_s") or 60)
        print(f"[generate] t={time.time() - t0:.2f}s rate_limited uid={uid[:10]} wait={wait}s", file=sys.stderr, flush=True)
        return JSONResponse(
            {"success": False,
             "message": f"You're going fast! Please wait about {wait}s and try again.",
             "retry_after": wait},
            status_code=429, headers={"Retry-After": str(wait)},
        )

    # Load-shed above the global in-flight cap. Not queued: a queued generate
    # would lose its result (no delivery path), so shed cleanly instead.
    if _in_flight > C.IN_FLIGHT_CAP:
        print(f"[generate] load-shed: in_flight={_in_flight}", file=sys.stderr, flush=True)
        return JSONResponse(
            {"error": "high_load", "message": "Server busy — please try again shortly."},
            status_code=503, headers={"Retry-After": "10"},
        )

    # 4) route to the pool (with fallback inside router)
    account = await router.pick_account(env, time.strftime("%Y-%m-%d", time.gmtime()),
                                        int(time.time()), sticky_key=title)
    if not account:
        return JSONResponse({"error": "provider pool exhausted"}, status_code=503,
                            headers={"Retry-After": "60"})
    print(f"[generate] t={time.time() - t0:.2f}s account picked id={account.get('id')}", file=sys.stderr, flush=True)

    result = await router.execute_request(
        env, user_id=uid, account=account, sticky_key=title,
        payload={"model": prompts.GENERATE_MODEL, "messages": messages,
                 "temperature": 0.0, "max_tokens": 1024},
    )
    print(f"[generate] t={time.time() - t0:.2f}s provider done status={result.get('status')} latency={result.get('latency_ms')}ms", file=sys.stderr, flush=True)

    # 5) log usage (batched flusher)
    flusher = getattr(request.app.state, "flusher", None)
    if flusher is not None:
        flusher.log_usage(
            user_id=uid, account_id=result.get("account_id"), model=prompts.GENERATE_MODEL,
            cache_hit=result.get("cache_hit", False),
            latency_ms=result.get("latency_ms"), status=result.get("status", 503),
            error_msg=result.get("error_msg"),
            ts=int(time.time()),
        )
        await flusher.flush_now()

    if result.get("status", 0) >= 400 or not result.get("content"):
        status = result.get("status", 503)
        return JSONResponse(
            {"error": "generation_failed"},
            status_code=status,
            headers={"Retry-After": "60"} if status >= 500 else {},
        )

    parsed = _parse_generate(result.get("content", ""))
    if not parsed:
        # Provider returned 200 with unparseable content (empty/truncated
        # completion observed in production). Retry on FRESH accounts —
        # the response quality is per-request, another key usually parses.
        used = {result.get("account_id")}
        for retry in range(2):
            print(f"[generate] t={time.time() - t0:.2f}s parse-fail retry {retry + 1}/2", file=sys.stderr, flush=True)
            acct = await router.pick_account(env, time.strftime("%Y-%m-%d", time.gmtime()),
                                             int(time.time()), exclude=used)
            if not acct:
                break
            used.add(acct["id"])
            result = await router.execute_request(
                env, user_id=uid, account=acct, sticky_key=title,
                payload={"model": prompts.GENERATE_MODEL, "messages": messages,
                         "temperature": 0.0, "max_tokens": 1024},
            )
            parsed = _parse_generate(result.get("content", ""))
            if parsed:
                break
    if not parsed:
        return JSONResponse({"error": "generation_failed"}, status_code=502)
    print(f"[generate] t={time.time() - t0:.2f}s parsed+flushed", file=sys.stderr, flush=True)

    # 6) consume quota only after a successful generation
    await _consume_quota(env, uid)
    print(f"[generate] t={time.time() - t0:.2f}s quota consumed", file=sys.stderr, flush=True)

    tags, desc = parsed["tags"], parsed["description"]
    await cache.store_exact(env, key, json.dumps({"tags": tags, "description": desc}))
    if C.TIER_FREE == tier:
        await cache.store_semantic(env, uid, prompts.GENERATE_MODEL, sem_key_text,
                                   json.dumps({"tags": tags, "description": desc}))
    print(f"[generate] t={time.time() - t0:.2f}s cache stored", file=sys.stderr, flush=True)

    usage, retry_after = await _usage_for(env, uid, tier)
    print(f"[generate] t={time.time() - t0:.2f}s SUCCESS uid={uid[:10]} tags={len(tags)}", file=sys.stderr, flush=True)
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


async def _consume_quota(env, uid: str) -> dict:
    """Inc the user's QuotaDO after a successful generation (pro: no-op).

    Returns the verdict; ok=false with rate_limited=true means the user's
    spam guard tripped (caller should surface a friendly wait message)."""
    try:
        do = env.QUOTA.get(env.QUOTA.idFromName(uid))
        if do is not None:
            v = await do.inc()
            if isinstance(v, dict):
                return v
    except Exception:
        pass
    return {"ok": True}


async def _d1_used_today(env, uid: str) -> int:
    """Count today's successful generates from usage_log (D1 fallback when DO is down)."""
    try:
        import time
        today_ts = int(time.time() // 86400) * 86400  # start of UTC day
        result = await env.DB.prepare(
            "SELECT COUNT(*) as cnt FROM usage_log WHERE user_id=?1 AND (status=200 OR status='200' OR status='ok' OR status<400) AND ts>=?2"
        ).bind(uid, today_ts).first()
        return int(result["cnt"]) if result and result.get("cnt") is not None else 0
    except Exception:
        return 0


async def _usage_for(env, uid: str, tier: str) -> tuple[dict, int]:
    """(usage, retry_after) calculated using D1 usage_log as source of truth for free tier."""
    if tier == C.TIER_PRO:
        return {"used": -1, "remaining": -1, "limit": -1, "plan": tier}, 0

    cfg = await db.get_free_quota(env)
    limit = -1 if cfg.get("cadence") == C.CADENCE_UNLIMITED else int(cfg.get("limit") or C.DEFAULT_FREE_DAILY_LIMIT)

    used = await _d1_used_today(env, uid)
    remaining = max(0, limit - used) if limit >= 0 else -1

    idx = min(max(used - 1, 0), len(C.GENERATE_DELAYS) - 1)
    result = {"used": used, "remaining": remaining, "limit": limit, "plan": tier}
    return result, C.GENERATE_DELAYS[idx]


@app.get("/v1/me")
async def me(request: Request):
    env = _bindings(request)
    auth = request.headers.get("Authorization", "")
    try:
        claims = await firebase.verify_token(auth.removeprefix("Bearer ").strip(), env)
    except firebase.AuthError as e:
        return _auth_reject(e)
    except Exception as e:
        return JSONResponse({"error": "unauthorized", "detail": str(e)}, status_code=401)

    try:
        uid = claims.get("uid", "")
        user = await db.get_user(env, uid) if uid else None
        tier = db.get_effective_tier(user) if user else C.TIER_FREE
        cf = (request.scope or {}).get("cf") or {}

        try:
            cfg = (await db.get_free_quota(env)) or {}
        except Exception:
            cfg = {}

        v_limit = (-1 if tier == C.TIER_PRO or cfg.get("cadence") == C.CADENCE_UNLIMITED
                   else int(cfg.get("limit") or C.DEFAULT_FREE_DAILY_LIMIT))

        if tier == C.TIER_PRO or v_limit == -1:
            v_remaining = -1
        else:
            used_today = await _d1_used_today(env, uid)
            v_remaining = max(0, v_limit - (used_today or 0))

        import time
        resets_in_seconds = max(0, int(86400 - (time.time() % 86400)))
        is_active = (user or {}).get("is_active", 1)

        billing_price_id = None
        sub_id = (user or {}).get("subscription_id")
        if tier == C.TIER_PRO and sub_id:
            try:
                sub = await db.get_subscription_by_id(env, sub_id)
                billing_price_id = (sub or {}).get("price_id")
            except Exception:
                pass

        return {
            "uid": uid,
            "email": claims.get("email") or (user or {}).get("email"),
            "tier": tier,
            "billing_price_id": billing_price_id,
            "is_active": is_active,
            "is_suspended": is_active == 0,
            "quota_remaining": 0 if is_active == 0 else v_remaining,
            "quota_limit": v_limit,
            "resets_in_seconds": resets_in_seconds,
            "geo": {"country": cf.get("country"), "region": cf.get("region"), "city": cf.get("city")},
        }
    except Exception as e:
        import sys; print(f"[error] /v1/me exception: {e}", file=sys.stderr, flush=True)
        return JSONResponse({"error": "internal", "detail": str(e)}, status_code=500)


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
# Paddle Billing Webhook & Security Best Practices
# --------------------------------------------------------------------------- #
_PADDLE_IPS_CACHE = {"ts": 0.0, "cidrs": []}


def _get_paddle_ip_cidrs() -> list[str]:
    """Fetch live Paddle IPv4 CIDRs dynamically from https://api.paddle.com/ips (cached 24h)."""
    now = time.time()
    if _PADDLE_IPS_CACHE["cidrs"] and (now - _PADDLE_IPS_CACHE["ts"]) < 86400:
        return _PADDLE_IPS_CACHE["cidrs"]
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.paddle.com/ips",
            headers={"User-Agent": "VidRank-Backend/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            cidrs = data.get("data", {}).get("ipv4_cidrs", [])
            if cidrs and isinstance(cidrs, list):
                _PADDLE_IPS_CACHE["cidrs"] = [str(c).strip() for c in cidrs]
                _PADDLE_IPS_CACHE["ts"] = now
                return _PADDLE_IPS_CACHE["cidrs"]
    except Exception as e:
        import sys
        print(f"[paddle-ips] Warning: failed to fetch live Paddle IPs ({e})", file=sys.stderr, flush=True)
    return _PADDLE_IPS_CACHE["cidrs"]


def _verify_paddle_ip(request: Request) -> bool:
    """Verify request client IP is within Paddle's published live CIDR ranges."""
    cidrs = _get_paddle_ip_cidrs()
    if not cidrs:
        return True  # If unable to fetch live IPs, do not hard-fail; rely on HMAC signature verification
    client_ip = (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "")
    )
    if not client_ip:
        return True
    try:
        import ipaddress
        ip = ipaddress.ip_address(client_ip.strip())
        for cidr in cidrs:
            if ip in ipaddress.ip_network(cidr, strict=False):
                return True
        return False
    except Exception:
        return True


def _verify_paddle_signature(raw_body: bytes, sig_header: str | None, secret_key: str) -> tuple[bool, str]:
    """Verify Paddle-Signature HMAC-SHA256 and timestamp freshness (replay attack prevention).
    
    Header format: ts=1690000000;h1=5d41402abc4b2a76b9719d911017c592...
    """
    if not secret_key:
        return False, "Missing PADDLE_WEBHOOK_SECRET_KEY"
    if not sig_header:
        return False, "Missing Paddle-Signature header"

    parts = {}
    for item in sig_header.split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k.strip()] = v.strip()

    ts_str = parts.get("ts")
    h1 = parts.get("h1")
    if not ts_str or not h1:
        return False, "Malformed Paddle-Signature header"

    try:
        ts = int(ts_str)
    except ValueError:
        return False, "Invalid timestamp in Paddle-Signature"

    # 5-minute replay attack tolerance
    if abs(time.time() - ts) > 300:
        return False, f"Paddle webhook timestamp expired or drifted (ts={ts}, now={int(time.time())})"

    import hmac
    import hashlib

    signed_payload = f"{ts}:{raw_body.decode('utf-8')}".encode("utf-8")
    expected_h1 = hmac.new(secret_key.strip().encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_h1, h1):
        return False, "Invalid signature hash"

    return True, "ok"


@app.post("/v1/billing/paddle-webhook")
@app.post("/v1/webhooks/paddle")
async def paddle_webhook(request: Request):
    """Secure Paddle Billing Webhook receiver for customer & subscription lifecycle events."""
    env = _bindings(request)
    
    # 1. IP allowlist check (optional best-effort, non-blocking if IPs unavailable)
    if not _verify_paddle_ip(request):
        import sys
        client_ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")
        print(f"[paddle-webhook] Blocked unauthorized IP: {client_ip}", file=sys.stderr, flush=True)
        return JSONResponse({"error": "unauthorized_ip"}, status_code=403)

    raw_body = await request.body()
    sig_header = request.headers.get("Paddle-Signature") or request.headers.get("paddle-signature")

    # Retrieve signing secret (supports sandbox and live)
    secret_key = (
        getattr(env, "PADDLE_WEBHOOK_SECRET_KEY", None)
        or getattr(env, "PADDLE_NOTIFICATION_SECRET", None)
        or os.environ.get("PADDLE_WEBHOOK_SECRET_KEY", "")
    )

    # 2. HMAC-SHA256 signature verification — Fail with 400 so Paddle retries
    if secret_key:
        valid, reason = _verify_paddle_signature(raw_body, sig_header, secret_key)
        if not valid:
            import sys
            print(f"[paddle-webhook] Signature verification failed: {reason}", file=sys.stderr, flush=True)
            return JSONResponse({"error": "invalid_signature", "reason": reason}, status_code=400)
    else:
        import sys
        print("[paddle-webhook] Warning: PADDLE_WEBHOOK_SECRET_KEY not set on environment", file=sys.stderr, flush=True)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        return JSONResponse({"error": "invalid_json", "details": str(e)}, status_code=400)

    event_id = payload.get("event_id", "")
    event_type = payload.get("event_type", "")
    data = payload.get("data", {}) or {}

    import sys
    print(f"[paddle-webhook] Processing event: {event_type} (id: {event_id})", file=sys.stderr, flush=True)

    # ── Part 1: Customer events ──────────────────────────────────────────────
    if event_type.startswith("customer."):
        customer_id = data.get("id", "")
        customer_email = (data.get("email") or "").strip().lower()
        if customer_id and customer_email:
            await db.upsert_customer(env, customer_id, customer_email)
            print(f"[paddle-webhook] Upserted customer {customer_id} ({customer_email})", file=sys.stderr, flush=True)

    # ── Part 2: Subscription events ──────────────────────────────────────────
    elif event_type.startswith("subscription."):
        sub_id = data.get("id", "")
        customer_id = data.get("customer_id", "")
        status = (data.get("status") or "").lower()
        items = data.get("items") or []
        price_id = ""
        product_id = ""
        if items and isinstance(items, list):
            price_info = items[0].get("price") or {}
            price_id = price_info.get("id") or items[0].get("price_id") or ""
            product_id = price_info.get("product_id") or items[0].get("product_id") or ""

        # Scheduled changes (e.g. action="cancel", effective_at="2026-09-01T00:00:00Z")
        scheduled_change = data.get("scheduled_change") or {}
        sched_action = scheduled_change.get("action")
        sched_at = scheduled_change.get("effective_at")

        # Upsert subscription mirror in D1
        if sub_id:
            await db.upsert_paddle_subscription(
                env,
                subscription_id=sub_id,
                customer_id=customer_id,
                status=status,
                price_id=price_id,
                product_id=product_id,
                scheduled_change_action=sched_action,
                scheduled_change_at=sched_at,
            )

        # Upsert customer mirror if customer email is available
        customer_data = data.get("customer") or {}
        customer_email = (customer_data.get("email") or "").strip().lower()
        if customer_id and customer_email:
            await db.upsert_customer(env, customer_id, customer_email)

        current_billing_period = data.get("current_billing_period") or {}
        ends_at = current_billing_period.get("ends_at") or data.get("next_billed_at")
        custom_data = data.get("custom_data") or {}

        # Resolve user in VidRank users table
        uid = custom_data.get("firebase_uid") or custom_data.get("user_id") or ""
        email = custom_data.get("email") or customer_email
        
        user = None
        if uid:
            user = await db.get_user(env, uid)
        if not user and email:
            user = await db.get_user_by_email(env, email)

        if user:
            target_uid = user["firebase_uid"]
            # Access granting rule: Active AND Trialing grant access.
            # Scheduled cancellation does NOT revoke access until status actually changes to canceled/expired!
            if status in ("active", "trialing"):
                await db.update_user_subscription(
                    env,
                    target_uid,
                    tier=C.TIER_PRO,
                    subscription_id=sub_id,
                    expires_at=ends_at,
                )
                print(f"[paddle-webhook] Granted PRO access to {target_uid} (sub: {sub_id}, status: {status})", file=sys.stderr, flush=True)
            elif status in ("canceled", "past_due", "paused"):
                now_ts = time.time()
                is_expired = True
                if ends_at:
                    try:
                        from datetime import datetime
                        dt = datetime.fromisoformat(str(ends_at).replace("Z", "+00:00"))
                        if dt.timestamp() > now_ts:
                            is_expired = False
                    except Exception:
                        pass
                if is_expired:
                    await db.update_user_subscription(
                        env,
                        target_uid,
                        tier=C.TIER_FREE,
                        subscription_id=sub_id,
                        expires_at=ends_at,
                    )
                    print(f"[paddle-webhook] Reverted user {target_uid} to FREE (status: {status})", file=sys.stderr, flush=True)
                else:
                    print(f"[paddle-webhook] Sub {sub_id} is {status} but period ends at {ends_at}; access maintained.", file=sys.stderr, flush=True)
        else:
            print(f"[paddle-webhook] User not found for subscription {sub_id} (uid={uid}, email={email})", file=sys.stderr, flush=True)

    # ── Part 3: Transaction events ───────────────────────────────────────────
    elif event_type.startswith("transaction."):
        tx_id = data.get("id") or ""
        status = (data.get("status") or "").lower()
        custom_data = data.get("custom_data") or {}
        sub_id = data.get("subscription_id")
        customer_id = data.get("customer_id") or ""
        customer_data = data.get("customer") or {}
        customer_email = (customer_data.get("email") or custom_data.get("email") or "").strip().lower()

        totals = data.get("details", {}).get("totals", {})
        total_str = totals.get("total", "0")
        currency = totals.get("currency_code", "USD")
        try:
            amount_cents = int(total_str)
        except (ValueError, TypeError):
            amount_cents = 0

        # Payments details
        payments = data.get("payments") or []
        card_brand = "Card"
        card_last4 = ""
        if payments and isinstance(payments, list):
            m_details = (payments[0].get("method_details") or {}).get("card") or {}
            card_brand = (m_details.get("type") or "Card").capitalize()
            card_last4 = m_details.get("last4") or ""

        billed_at = data.get("billed_at") or data.get("created_at")
        invoice_id = data.get("invoice_id")
        invoice_number = data.get("invoice_number")

        uid = custom_data.get("firebase_uid") or custom_data.get("user_id") or ""
        user = None
        if uid:
            user = await db.get_user(env, uid)
        if not user and customer_email:
            user = await db.get_user_by_email(env, customer_email)

        target_uid = user.get("firebase_uid") if user else uid

        # Upsert payment in D1 payments table
        if tx_id and customer_id:
            await db.upsert_payment(
                env,
                payment_id=tx_id,
                customer_id=customer_id,
                subscription_id=sub_id,
                user_id=target_uid,
                email=customer_email,
                amount_cents=amount_cents,
                currency=currency,
                status=status,
                card_brand=card_brand,
                card_last4=card_last4,
                invoice_id=invoice_id,
                invoice_number=invoice_number,
                billed_at=billed_at,
            )

        if customer_id and customer_email:
            await db.upsert_customer(env, customer_id, customer_email)

        if status in ("completed", "paid") and target_uid:
            from datetime import datetime, timedelta, timezone
            expires_at = (datetime.now(timezone.utc) + timedelta(days=32)).isoformat()
            await db.update_user_subscription(
                env,
                target_uid,
                tier=C.TIER_PRO,
                subscription_id=sub_id,
                expires_at=expires_at,
            )
            print(f"[paddle-webhook] Transaction {tx_id} saved: user {target_uid} confirmed PRO", file=sys.stderr, flush=True)

    return JSONResponse({"status": "ok", "event_id": event_id})


# --------------------------------------------------------------------------- #
# Paddle HTTP Helper (using Cloudflare Workers native js_fetch)
# --------------------------------------------------------------------------- #
async def _paddle_http_call(method: str, url: str, api_key: str, body: dict | None = None) -> tuple[int, dict]:
    """Execute an outbound HTTP request to Paddle API safely in Cloudflare Workers using js_fetch."""
    try:
        from js import fetch as js_fetch, JSON as js_JSON
        init_dict = {
            "method": method,
            "headers": {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        }
        if body is not None:
            init_dict["body"] = json.dumps(body)

        init = js_JSON.parse(json.dumps(init_dict))
        resp = await js_fetch(url, init)
        raw = await resp.text()
        status = int(getattr(resp, "status", 200))
        data = json.loads(raw) if raw else {}
        return status, data
    except ImportError:
        # Local development fallback
        import urllib.request
        import urllib.error
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        req_data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                raw = resp.read().decode("utf-8")
                return resp.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8")
            return e.code, json.loads(raw) if raw else {"error": str(e)}
        except Exception as e:
            return 500, {"error": str(e)}


# --------------------------------------------------------------------------- #
# Customer Portal Session Minting (Paddle Self-Service Portal)
# --------------------------------------------------------------------------- #
@app.post("/v1/billing/customer-portal")
async def get_customer_portal_session(request: Request):
    """Mint a Paddle customer portal session URL for the authenticated user."""
    env = _bindings(request)
    
    # 1. Authenticate user from Firebase Bearer Token
    auth_header = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not auth_header:
        return JSONResponse({"error": "missing_authorization_header"}, status_code=401)

    try:
        claims = await firebase.verify_token(auth_header, env)
    except firebase.AuthError as e:
        return _auth_reject(e)

    uid = claims.get("uid", "")
    email = (claims.get("email") or "").strip().lower()
    
    user = await db.get_user(env, uid)
    if not user:
        return JSONResponse({"error": "user_not_found"}, status_code=404)

    # 2. Resolve Paddle customer ID server-side
    customer_id = None
    if email:
        cust_row = await db.get_customer_by_email(env, email)
        if cust_row:
            cid = cust_row.get("customer_id")
            if cid and not str(cid).startswith("ctm_sandbox_test"):
                customer_id = cid

    sub_id = user.get("subscription_id")
    if not customer_id and sub_id:
        sub_row = await db.get_subscription_by_id(env, sub_id)
        if sub_row:
            cid = sub_row.get("customer_id")
            if cid and not str(cid).startswith("ctm_sandbox_test"):
                customer_id = cid

    # API credentials
    api_key = (
        getattr(env, "PADDLE_API_KEY", None)
        or os.environ.get("PADDLE_API_KEY", "")
    )
    paddle_env = (
        getattr(env, "PUBLIC_PADDLE_ENVIRONMENT", None)
        or getattr(env, "PADDLE_ENVIRONMENT", "sandbox")
    )
    is_sandbox = "sdbx" in api_key or paddle_env == "sandbox"
    base_url = "https://sandbox-api.paddle.com" if is_sandbox else "https://api.paddle.com"

    # If customer_id not found in DB, try looking up via Paddle API by email
    if (not customer_id or str(customer_id).startswith("ctm_sandbox_test")) and email and api_key:
        try:
            lookup_url = f"{base_url}/customers?email={email}"
            status, lookup_data = await _paddle_http_call("GET", lookup_url, api_key)
            if status == 200:
                customers_found = lookup_data.get("data", [])
                if customers_found:
                    customer_id = customers_found[0].get("id")
                    if customer_id:
                        await db.upsert_customer(env, customer_id, email)
        except Exception as e:
            import sys
            print(f"[customer-portal] Paddle customer lookup error: {e}", file=sys.stderr, flush=True)

    if not customer_id:
        return JSONResponse({
            "error": "no_paddle_customer",
            "message": "No active billing profile found for your account. Subscribe to a plan first."
        }, status_code=404)

    # 3. Mint Portal Session with Paddle API
    try:
        portal_url = f"{base_url}/customers/{customer_id}/portal-sessions"
        status, portal_res = await _paddle_http_call("POST", portal_url, api_key, body={})
        if status not in (200, 201):
            err_msg = portal_res.get("error", {}).get("detail") or json.dumps(portal_res)
            return JSONResponse({"error": "paddle_portal_error", "details": err_msg}, status_code=status)

        urls = portal_res.get("data", {}).get("urls", {})
        general_url = (urls.get("general") or {}).get("overview") or urls.get("overview")
        return JSONResponse({
            "success": True,
            "url": general_url,
            "customer_id": customer_id,
            "urls": urls
        })
    except Exception as e:
        import sys
        print(f"[customer-portal] Exception: {e}", file=sys.stderr, flush=True)
        return JSONResponse({"error": "portal_session_failed", "details": str(e)}, status_code=500)


# --------------------------------------------------------------------------- #
# Direct Paddle PDF Invoice / Receipt Downloader
# --------------------------------------------------------------------------- #
@app.get("/v1/billing/invoice-pdf")
async def get_invoice_pdf_url(request: Request):
    """Retrieve direct Paddle S3 PDF download URL for a given transaction."""
    env = _bindings(request)
    auth_header = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not auth_header:
        return JSONResponse({"error": "missing_authorization_header"}, status_code=401)

    try:
        claims = await firebase.verify_token(auth_header, env)
    except firebase.AuthError as e:
        return _auth_reject(e)

    transaction_id = request.query_params.get("transaction_id", "").strip()
    if not transaction_id:
        return JSONResponse({"error": "missing_transaction_id"}, status_code=400)

    api_key = getattr(env, "PADDLE_API_KEY", None) or os.environ.get("PADDLE_API_KEY", "")
    paddle_env = getattr(env, "PUBLIC_PADDLE_ENVIRONMENT", None) or getattr(env, "PADDLE_ENVIRONMENT", "sandbox")
    is_sandbox = "sdbx" in api_key or paddle_env == "sandbox"
    base_url = "https://sandbox-api.paddle.com" if is_sandbox else "https://api.paddle.com"

    try:
        url = f"{base_url}/transactions/{transaction_id}/invoice"
        status, data = await _paddle_http_call("GET", url, api_key)
        pdf_url = data.get("data", {}).get("url")
        if not pdf_url:
            return JSONResponse({"error": "pdf_not_found", "details": data}, status_code=404)
        return JSONResponse({"success": True, "url": pdf_url})
    except Exception as e:
        import sys
        print(f"[invoice-pdf] Exception: {e}", file=sys.stderr, flush=True)
        return JSONResponse({"error": "failed_to_fetch_pdf", "details": str(e)}, status_code=500)


# --------------------------------------------------------------------------- #
# Switch Billing Period (monthly <-> yearly) — updates the SAME subscription
# so a plan change never creates a duplicate one.
# --------------------------------------------------------------------------- #
@app.post("/v1/billing/switch-plan")
async def switch_billing_plan(request: Request):
    """Switch the user's active subscription between monthly and yearly prices.

    Body: {"price_id": "pri_..."} — must differ from the current price.
    """
    env = _bindings(request)
    auth_header = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not auth_header:
        return JSONResponse({"error": "missing_authorization_header"}, status_code=401)
    try:
        claims = await firebase.verify_token(auth_header, env)
    except firebase.AuthError as e:
        return _auth_reject(e)

    body = await _read_json(request) or {}
    new_price_id = str(body.get("price_id") or "").strip()
    if not new_price_id.startswith("pri_"):
        return JSONResponse({"error": "bad_request", "message": "price_id required (pri_...)"}, status_code=400)

    uid = claims.get("uid", "")
    user = await db.get_user(env, uid)
    if not user:
        user = await db.get_user_by_email(env, (claims.get("email") or "").strip().lower())
    sub_id = (user or {}).get("subscription_id")
    if not sub_id:
        return JSONResponse({"error": "no_active_subscription", "message": "Buy a Pro plan first."}, status_code=404)

    current = await db.get_subscription_by_id(env, sub_id) or {}
    if current.get("price_id") == new_price_id:
        return JSONResponse({"error": "already_on_this_plan"}, status_code=409)

    api_key = getattr(env, "PADDLE_API_KEY", None) or os.environ.get("PADDLE_API_KEY", "")
    is_sandbox = "sdbx" in api_key
    base_url = "https://sandbox-api.paddle.com" if is_sandbox else "https://api.paddle.com"

    try:
        url = f"{base_url}/subscriptions/{sub_id}"
        status, data = await _paddle_http_call("PATCH", url, api_key, body={
            "items": [{"price_id": new_price_id, "quantity": 1}],
            "proration_billing_mode": "prorated_immediately",
        })
        if status not in (200, 201):
            return JSONResponse({"error": "paddle_switch_error", "details": data}, status_code=status)

        items = (data.get("data") or {}).get("items") or [{}]
        new_price = (items[0].get("price") or {}).get("id") or new_price_id
        await db.upsert_paddle_subscription(
            env, subscription_id=sub_id,
            customer_id=data.get("data", {}).get("customer_id", ""),
            status=data.get("data", {}).get("status", "active"),
            price_id=new_price,
        )
        return {"success": True, "message": "Billing period switched.", "subscription": data.get("data")}
    except Exception as e:
        print(f"[switch-plan] Exception: {e}", file=sys.stderr, flush=True)
        return JSONResponse({"error": "switch_failed", "details": str(e)}, status_code=500)


@app.post("/v1/billing/cancel-subscription")
async def cancel_user_subscription(request: Request):
    """Cancel user's recurring subscription effective at the end of the current billing cycle."""
    env = _bindings(request)
    auth_header = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not auth_header:
        return JSONResponse({"error": "missing_authorization_header"}, status_code=401)

    try:
        claims = await firebase.verify_token(auth_header, env)
    except firebase.AuthError as e:
        return _auth_reject(e)

    uid = claims.get("uid", "")
    email = (claims.get("email") or "").strip().lower()

    user = await db.get_user(env, uid)
    if not user and email:
        user = await db.get_user_by_email(env, email)

    sub_id = (user or {}).get("subscription_id")
    if not sub_id:
        cust = await db.get_customer_by_email(env, email) if email else None
        if cust:
            sub_row = await db._fetch_one(
                env,
                "SELECT subscription_id FROM subscriptions WHERE customer_id = ?1 AND status IN ('active', 'trialing') ORDER BY updated_at DESC LIMIT 1",
                cust.get("customer_id")
            )
            if sub_row:
                sub_id = sub_row.get("subscription_id")

    if not sub_id:
        return JSONResponse({"error": "no_active_subscription", "message": "No active subscription found to cancel."}, status_code=404)

    api_key = getattr(env, "PADDLE_API_KEY", None) or os.environ.get("PADDLE_API_KEY", "")
    paddle_env = getattr(env, "PUBLIC_PADDLE_ENVIRONMENT", None) or getattr(env, "PADDLE_ENVIRONMENT", "sandbox")
    is_sandbox = "sdbx" in api_key or paddle_env == "sandbox"
    base_url = "https://sandbox-api.paddle.com" if is_sandbox else "https://api.paddle.com"

    try:
        url = f"{base_url}/subscriptions/{sub_id}/cancel"
        status, data = await _paddle_http_call("POST", url, api_key, body={"effective_from": "next_billing_period"})
        if status not in (200, 201):
            return JSONResponse({"error": "paddle_cancel_error", "details": data}, status_code=status)

        sched_at = data.get("data", {}).get("scheduled_change", {}).get("effective_at")
        await db.upsert_paddle_subscription(
            env,
            subscription_id=sub_id,
            customer_id=data.get("data", {}).get("customer_id", ""),
            status=data.get("data", {}).get("status", "active"),
            scheduled_change_action="cancel",
            scheduled_change_at=sched_at,
        )

        return JSONResponse({
            "success": True,
            "message": "Subscription cancellation scheduled successfully. Pro access remains active until the end of the billing period.",
            "effective_at": sched_at,
            "subscription": data.get("data")
        })
    except Exception as e:
        import sys
        print(f"[cancel-subscription] Exception: {e}", file=sys.stderr, flush=True)
        return JSONResponse({"error": "cancel_failed", "details": str(e)}, status_code=500)


# --------------------------------------------------------------------------- #
# User Dashboard Data: Usage Graph & Paddle Billing / Payment History
# --------------------------------------------------------------------------- #
@app.get("/v1/user/dashboard-data")
async def get_user_dashboard_data(request: Request):
    """Return consolidated usage chart data, subscription metrics, and billing records."""
    env = _bindings(request)
    auth_header = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not auth_header:
        return JSONResponse({"error": "missing_authorization_header"}, status_code=401)

    try:
        claims = await firebase.verify_token(auth_header, env)
    except firebase.AuthError as e:
        return _auth_reject(e)

    uid = claims.get("uid", "")
    email = (claims.get("email") or "").strip().lower()

    user = await db.get_user(env, uid)
    if not user:
        user = await db.get_user_by_email(env, email)

    tier = db.get_effective_tier(user) if user else C.TIER_FREE

    # 1. Quota & Limits
    try:
        cfg = (await db.get_free_quota(env)) or {}
    except Exception:
        cfg = {}

    v_limit = (-1 if tier == C.TIER_PRO or cfg.get("cadence") == C.CADENCE_UNLIMITED
               else int(cfg.get("limit") or C.DEFAULT_FREE_DAILY_LIMIT))
    used_today = await _d1_used_today(env, uid) if uid else 0
    v_remaining = -1 if (tier == C.TIER_PRO or v_limit == -1) else max(0, v_limit - (used_today or 0))
    resets_in_seconds = max(0, int(86400 - (time.time() % 86400)))

    # 2. 14-Day Usage Graph Data
    cutoff_ts = int(time.time()) - (14 * 86400)
    usage_rows = await db._fetch_all(
        env,
        "SELECT substr(date(ts, 'unixepoch'), 1, 10) AS day, "
        "       COUNT(*) AS total_requests, "
        "       SUM(CASE WHEN cache_hit THEN 1 ELSE 0 END) AS cache_hits "
        "FROM usage_log "
        "WHERE user_id = ?1 AND ts >= ?2 "
        "GROUP BY day ORDER BY day ASC",
        uid, cutoff_ts,
    )

    # 3. Subscription & Customer Mirror
    customer_id = None
    if email:
        cust_row = await db.get_customer_by_email(env, email)
        if cust_row:
            customer_id = cust_row.get("customer_id")

    sub_row = None
    sub_id = (user or {}).get("subscription_id")
    if sub_id:
        sub_row = await db.get_subscription_by_id(env, sub_id)
        if sub_row and not customer_id:
            customer_id = sub_row.get("customer_id")
    elif customer_id:
        sub_row = await db._fetch_one(
            env, "SELECT * FROM subscriptions WHERE customer_id = ?1 ORDER BY updated_at DESC LIMIT 1", customer_id
        )

    # 4. Paddle Transactions & Invoices
    api_key = getattr(env, "PADDLE_API_KEY", None) or os.environ.get("PADDLE_API_KEY", "")
    paddle_env = getattr(env, "PUBLIC_PADDLE_ENVIRONMENT", None) or getattr(env, "PADDLE_ENVIRONMENT", "sandbox")
    is_sandbox = "sdbx" in api_key or paddle_env == "sandbox"
    base_url = "https://sandbox-api.paddle.com" if is_sandbox else "https://api.paddle.com"

    transactions_list = []
    total_paid_cents = 0

    target_customer_ids = set()
    if customer_id and not str(customer_id).startswith("ctm_sandbox_test"):
        target_customer_ids.add(customer_id)

    if api_key and email:
        try:
            c_url = f"{base_url}/customers?email={email}"
            c_status, c_data = await _paddle_http_call("GET", c_url, api_key)
            if c_status == 200:
                for c_item in c_data.get("data", []):
                    cid = c_item.get("id")
                    if cid:
                        target_customer_ids.add(cid)
                        customer_id = cid
                        await db.upsert_customer(env, cid, email)
        except Exception:
            pass

    seen_tx_ids = set()
    for cid in target_customer_ids:
        try:
            t_url = f"{base_url}/transactions?customer_id={cid}&order_by=created_at[DESC]"
            t_status, t_data = await _paddle_http_call("GET", t_url, api_key)
            if t_status == 200:
                for tx in t_data.get("data", []):
                    tx_id = tx.get("id")
                    if not tx_id or tx_id in seen_tx_ids:
                        continue
                    seen_tx_ids.add(tx_id)
                    status = tx.get("status", "")
                    
                    # Filter out draft/incomplete/ready attempts - only show actual completed/paid invoices
                    if status not in ("completed", "paid"):
                        continue

                    totals = tx.get("details", {}).get("totals", {})
                    total_str = totals.get("total", "0")
                    currency = totals.get("currency_code", "USD")
                    
                    try:
                        cents = int(total_str)
                    except (ValueError, TypeError):
                        cents = 0

                    if cents == 0:
                        # Skip $0 trial authorization setup rows
                        continue

                    total_paid_cents += cents

                    # Card info
                    payments = tx.get("payments", [])
                    card_brand = "Card"
                    card_last4 = ""
                    if payments and isinstance(payments, list):
                        m_details = (payments[0].get("method_details") or {}).get("card") or {}
                        card_brand = (m_details.get("type") or "Card").capitalize()
                        card_last4 = m_details.get("last4") or ""

                    # Persist to local DB payments table
                    try:
                        await db.upsert_payment(
                            env,
                            payment_id=tx_id,
                            customer_id=cid,
                            subscription_id=tx.get("subscription_id"),
                            user_id=uid,
                            email=email,
                            amount_cents=cents,
                            currency=currency,
                            status=status,
                            card_brand=card_brand,
                            card_last4=card_last4,
                            invoice_id=tx.get("invoice_id"),
                            invoice_number=tx.get("invoice_number"),
                            billed_at=tx.get("billed_at") or tx.get("created_at"),
                        )
                    except Exception:
                        pass

                    formatted_amt = f"${(cents / 100):.2f} {currency}"

                    transactions_list.append({
                        "id": tx_id,
                        "status": status,
                        "amount": formatted_amt,
                        "currency": currency,
                        "date": tx.get("billed_at") or tx.get("created_at"),
                        "invoice_number": tx.get("invoice_number"),
                        "invoice_id": tx.get("invoice_id"),
                        "card_brand": card_brand,
                        "card_last4": card_last4,
                    })
        except Exception as err:
            import sys
            print(f"[dashboard-data] Transaction fetch error for {cid}: {err}", file=sys.stderr, flush=True)

    # Fallback to DB payments if Paddle API returned empty
    if not transactions_list:
        try:
            db_payments = await db.get_payments_for_user(env, email=email, customer_id=customer_id, user_id=uid)
            for p in db_payments:
                p_cents = p.get("amount_cents") or 0
                p_curr = p.get("currency") or "USD"
                p_status = p.get("status") or "completed"
                if p_status not in ("completed", "paid") or p_cents == 0:
                    continue
                total_paid_cents += p_cents
                transactions_list.append({
                    "id": p.get("id"),
                    "status": p_status,
                    "amount": f"${(p_cents / 100):.2f} {p_curr}",
                    "currency": p_curr,
                    "date": p.get("billed_at") or p.get("created_at"),
                    "invoice_number": p.get("invoice_number"),
                    "invoice_id": p.get("invoice_id"),
                    "card_brand": p.get("card_brand") or "Card",
                    "card_last4": p.get("card_last4") or "",
                })
        except Exception:
            pass

    # Build enhanced subscription object with exact pricing and billing cycle
    sub_dict = dict(sub_row) if sub_row else {}
    price_id = sub_dict.get("price_id") or ""
    is_yearly = False
    
    if "year" in price_id.lower() or "pri_01m0ttns" in price_id:
        is_yearly = True
    elif total_paid_cents > 1500 or any(float((t.get("amount") or "0").replace("$", "").split()[0]) > 10 for t in transactions_list):
        is_yearly = True
    elif user and user.get("expires_at"):
        try:
            import datetime as dt
            exp_str = str(user["expires_at"]).replace("Z", "+00:00")
            exp_d = dt.datetime.fromisoformat(exp_str)
            if (exp_d - dt.datetime.now(dt.timezone.utc)).days > 60:
                is_yearly = True
        except Exception:
            pass

    if tier == C.TIER_PRO:
        sub_dict["is_yearly"] = is_yearly
        sub_dict["interval"] = "year" if is_yearly else "month"
        sub_dict["billing_cycle"] = "Yearly recurring" if is_yearly else "Monthly recurring"
        sub_dict["formatted_price"] = "$38.30 / year" if is_yearly else "$3.99 / month"
        sub_dict["plan_name"] = "VidRank Pro Yearly" if is_yearly else "VidRank Pro Monthly"
    else:
        sub_dict["is_yearly"] = False
        sub_dict["interval"] = "none"
        sub_dict["billing_cycle"] = "No recurring cycle"
        sub_dict["formatted_price"] = "$0.00 / free"
        sub_dict["plan_name"] = "Free Plan"

    return JSONResponse({
        "user": {
            "uid": uid,
            "email": email,
            "name": (user or {}).get("name") or claims.get("name") or email.split("@")[0],
            "photo_url": (user or {}).get("photo_url") or claims.get("picture"),
            "tier": tier,
            "is_active": (user or {}).get("is_active", 1),
            "expires_at": (user or {}).get("expires_at"),
        },
        "quota": {
            "tier": tier,
            "remaining": v_remaining,
            "limit": v_limit,
            "used_today": used_today or 0,
            "resets_in_seconds": resets_in_seconds,
        },
        "usage_chart": usage_rows,
        "subscription": sub_dict,
        "billing": {
            "customer_id": customer_id,
            "total_paid": f"${(total_paid_cents / 100):.2f}",
            "transactions": transactions_list,
        }
    })





# --------------------------------------------------------------------------- #
# admin API
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# Cookie helpers
# --------------------------------------------------------------------------- #
_REFRESH_COOKIE = "admin_refresh"
_REFRESH_MAX_AGE = admin_mod.REFRESH_TOKEN_TTL_S


def _set_refresh_cookie(response: JSONResponse, token: str) -> JSONResponse:
    """Attach the httpOnly refresh-token cookie to a JSONResponse."""
    # SameSite=None + Secure required for cross-origin (Pages → Workers).
    # In local dev (http://localhost) the browser may ignore Secure; that is fine.
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=_REFRESH_MAX_AGE,
        path="/admin",
    )
    return response


def _clear_refresh_cookie(response: JSONResponse) -> JSONResponse:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value="",
        httponly=True,
        secure=True,
        samesite="none",
        max_age=0,
        path="/admin",
    )
    return response


def _read_refresh_cookie(request: Request) -> str:
    """Read admin_refresh cookie from the request."""
    cookie_header = request.headers.get("cookie", "")
    for part in cookie_header.split(";"):
        part = part.strip()
        if part.startswith(f"{_REFRESH_COOKIE}="):
            return part[len(_REFRESH_COOKIE) + 1:]
    return ""


# --------------------------------------------------------------------------- #
# /admin/login  (POST — credentials, GET — session probe)
# --------------------------------------------------------------------------- #
@app.api_route("/admin/login", methods=["POST", "GET", "PUT", "PATCH"])
async def admin_login(request: Request):
    """Login.

    POST {password}                     — super admin login
    POST {username, password}           — sub-admin login
    GET  (with valid admin_refresh cookie) — returns current session info
                                           so the frontend can restore state
                                           after a page reload without re-login.
    """
    env = _bindings(request)

    # GET: non-destructive session probe — validate refresh cookie and return
    # current role/username so the frontend can restore in-memory access token.
    if request.method == "GET":
        refresh_tok = _read_refresh_cookie(request)
        if not refresh_tok:
            return JSONResponse({"status": "no_session"}, status_code=401)
        claims = admin_mod.verify_jwt(env, refresh_tok, expected_type="refresh")
        if not claims:
            resp = JSONResponse({"status": "session_expired"}, status_code=401)
            return _clear_refresh_cookie(resp)
        # Issue a fresh access token so the frontend can continue seamlessly.
        access_token = admin_mod.issue_access_token(env, claims["role"], claims["sid"])
        username = None
        if claims["role"] == "sub" and claims.get("sid"):
            sub = await db.get_sub_admin(env, claims["sid"])
            username = (sub or {}).get("username")
        return JSONResponse({
            "ok": True,
            "access_token": access_token,
            "access_token_ttl_s": admin_mod.ACCESS_TOKEN_TTL_S,
            "role": claims["role"],
            "username": username,
        })

    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)

    username_in = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")

    # --- sub-admin login ---
    if username_in:
        sub = await db.get_sub_admin_by_username(env, username_in)
        if not sub or not sub.get("is_active"):
            return JSONResponse({"error": "invalid_credentials"}, status_code=401)
        if not admin_mod.verify_sub_password(password, sub.get("pass_hash") or ""):
            return JSONResponse({"error": "invalid_credentials"}, status_code=401)
        access_token  = admin_mod.issue_access_token(env,  role="sub", sid=sub["id"])
        refresh_token = admin_mod.issue_refresh_token(env, role="sub", sid=sub["id"])
        resp = JSONResponse({
            "ok": True,
            "access_token": access_token,
            "access_token_ttl_s": admin_mod.ACCESS_TOKEN_TTL_S,
            "role": "sub",
            "username": sub["username"],
        })
        return _set_refresh_cookie(resp, refresh_token)

    # --- super-admin login ---
    if not admin_mod.check_admin_password(env, password):
        return JSONResponse({"error": "invalid_credentials"}, status_code=401)
    access_token  = admin_mod.issue_access_token(env)
    refresh_token = admin_mod.issue_refresh_token(env)
    resp = JSONResponse({
        "ok": True,
        "access_token": access_token,
        "access_token_ttl_s": admin_mod.ACCESS_TOKEN_TTL_S,
        "role": "admin",
    })
    return _set_refresh_cookie(resp, refresh_token)


# --------------------------------------------------------------------------- #
# /admin/refresh  — silent re-issue of access token using refresh cookie
# --------------------------------------------------------------------------- #
@app.post("/admin/refresh")
async def admin_refresh(request: Request):
    """Exchange valid refresh cookie for a new access token (silent re-auth)."""
    env = _bindings(request)
    refresh_tok = _read_refresh_cookie(request)
    if not refresh_tok:
        return JSONResponse({"error": "no_refresh_cookie"}, status_code=401)
    claims = admin_mod.verify_jwt(env, refresh_tok, expected_type="refresh")
    if not claims:
        resp = JSONResponse({"error": "refresh_token_invalid"}, status_code=401)
        return _clear_refresh_cookie(resp)
    access_token = admin_mod.issue_access_token(env, claims["role"], claims["sid"])
    return JSONResponse({
        "ok": True,
        "access_token": access_token,
        "access_token_ttl_s": admin_mod.ACCESS_TOKEN_TTL_S,
        "role": claims["role"],
    })


# --------------------------------------------------------------------------- #
# /admin/logout  — invalidate session by clearing refresh cookie
# --------------------------------------------------------------------------- #
@app.post("/admin/logout")
async def admin_logout(request: Request):
    """Clear the refresh-token cookie (client must also discard access token)."""
    resp = JSONResponse({"ok": True})
    return _clear_refresh_cookie(resp)


# --------------------------------------------------------------------------- #
# Auth guard helpers (used by all other admin routes)
# --------------------------------------------------------------------------- #
async def _admin(request: Request) -> dict | None:
    """Verify the access JWT from Authorization: Bearer header."""
    env = _bindings(request)
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return admin_mod.verify_jwt(env, token, expected_type="access")


async def _super(request: Request) -> bool:
    auth = await _admin(request)
    return bool(auth and auth.get("role") == "admin")


async def _log_sub_activity(env, auth: dict | None, action: str, uid: str,
                            details: dict | None = None) -> None:
    """Audit-log a sub-admin's user-table action. No-op for super admins."""
    if not auth or auth.get("role") != "sub":
        return
    sub = await db.get_sub_admin(env, auth.get("sid")) if auth.get("sid") else None
    user = await db.get_user(env, uid)
    await db.add_sub_admin_activity(
        env,
        sub_admin_id=auth.get("sid") or "?",
        sub_admin_username=(sub or {}).get("username") or "?",
        action=action,
        target_uid=uid,
        target_email=(user or {}).get("email"),
        details=details,
    )


@app.get("/admin/accounts")
async def admin_list_accounts(request: Request):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return {"accounts": await db.list_enabled_accounts(env)}


@app.get("/admin/accounts/all")
async def admin_list_all_accounts(request: Request):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    accounts, err = await _t(db.list_accounts(env), 5.0)
    if err:
        return JSONResponse({"error": "db_timeout"}, status_code=504)
    for a in accounts or []:
        a["key_preview"] = admin_mod.mask_key(env, a.pop("key_enc", "")) if a.get("key_enc") else ""
    return {"accounts": accounts or []}


@app.get("/admin/accounts/usage")
async def admin_accounts_usage(request: Request, days: int = 7):
    """Per-account rollup chart data: usage vs limit, up to `days` back."""
    env = _bindings(request)
    if not await _super(request):
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


@app.get("/admin/accounts/usage/paged")
async def admin_accounts_usage_paged(
    request: Request,
    days: int = 7,
    q: str | None = None,
    provider: str | None = None,
    page: int = 1,
    page_size: int = 10,
):
    """Server-side paginated per-account usage rollup chart data.

    Uses a single bulk DB query for all page accounts instead of N serial
    queries — eliminates the pagination hang on large account pools.
    """
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    days = min(max(days, 1), 90)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    # Both count + list run in parallel via asyncio.gather
    total, accounts = await asyncio.gather(
        db.count_accounts(env, q, provider),
        db.list_accounts_paged(env, q, provider, page, page_size),
    )

    # Single bulk query for all accounts on this page (was N serial queries)
    account_ids = [a["id"] for a in accounts]
    rollups_by_id = await db.get_accounts_usage_days_bulk(env, account_ids, days)

    out = [
        {
            "id": a["id"],
            "provider": a["provider"],
            "label": a["label"],
            "daily_limit": a["daily_limit"],
            "rpm_limit": a["rpm_limit"],
            "enabled": a["enabled"],
            "days": rollups_by_id.get(a["id"], []),
        }
        for a in accounts
    ]

    return {
        "accounts": out,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }



@app.get("/admin/geo")
async def admin_geo(request: Request, days: int = 30):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    days = min(max(days, 1), 365)
    rows = await db._fetch_all(
        env,
        "SELECT country, region, city, COUNT(*) AS requests, "
        "COUNT(DISTINCT user_id) AS users FROM usage_log "
        "WHERE ts >= ?1 GROUP BY country, region, city ORDER BY requests DESC",
        int(time.time()) - days * 86400,
    )
    return {"geo": [r for r in rows if r.get("country") or r.get("city")]}


@app.post("/admin/accounts")
async def admin_add_account(request: Request):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    provider = body.get("provider", "")
    if provider not in ("openrouter", "groq"):
        return JSONResponse({"error": "provider must be openrouter|groq"}, status_code=400)
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
    if not await _super(request):
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
    new_key = body.get("key")
    if new_key:
        fields["key_enc"] = admin_mod.encrypt_key(env, new_key)
    await db.update_account(env, account_id, fields)
    return {"account_id": account_id, "updated": list(fields.keys())}


@app.delete("/admin/accounts/{account_id}")
async def admin_delete_account(request: Request, account_id: str):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    existing = await db.get_account(env, account_id)
    if not existing:
        return JSONResponse({"error": "not found"}, status_code=404)
    await db.delete_account(env, account_id)
    return {"deleted": account_id}


async def _t(coro, seconds: float = 5.0):
    # Guard against JS-bridge calls that hang forever — a clean timeout
    # surfaces as a logged error instead of a runtime "worker hung" cancel.
    try:
        return await asyncio.wait_for(coro, seconds), None
    except Exception as e:
        return None, e


@app.get("/admin/accounts/health")
async def admin_accounts_health(request: Request):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    out = {}
    accounts, err = await _t(db.list_enabled_accounts(env))
    if err:
        return JSONResponse({"error": "db_timeout"}, status_code=504)
    for a in accounts or []:
        try:
            h, terr = await _t(env.RATESTATE.get(env.RATESTATE.idFromName(a["id"])).get_health(), 3.0)
            out[a["id"]] = h if terr is None else {"health": None, "timeout": True}
        except Exception:
            out[a["id"]] = {"health": None}
    return {"health": out}


@app.get("/admin/accounts/{account_id}/usage")
async def admin_account_usage(request: Request, account_id: str):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    acc, _ = await _t(db.get_account(env, account_id), 5.0)
    live, _ = await _t(env.RATESTATE.get(env.RATESTATE.idFromName(account_id)).get_live(), 3.0)
    return {"live": live, "limit": (acc or {}).get("daily_limit"),
            "rpm_limit": (acc or {}).get("rpm_limit")}


@app.get("/admin/stats/latency")
async def admin_stats_latency(request: Request, hours: int = 24):
    """p50/p90/p99 latency + rotation health for REAL (non-cache) requests.

    The decision numbers for the capacity matrix: if p90 crosses ~5s for
    days, model/routing change is due; a high rotation_fail share means the
    pool is exhausted or accounts are unhealthy.
    """
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    hours = max(1, min(hours, 168))
    since = int(time.time()) - hours * 3600

    rows, _ = await _t(db._fetch_all(
        env,
        "SELECT latency_ms, status FROM usage_log "
        "WHERE ts > ? AND cache_hit = 0 AND latency_ms IS NOT NULL",
        since), 5.0)
    rows = rows or []

    lats = sorted(r["latency_ms"] for r in rows if r.get("latency_ms") is not None)

    def pct(p: float) -> int | None:
        if not lats:
            return None
        idx = min(len(lats) - 1, int(round((p / 100.0) * (len(lats) - 1))))
        return lats[idx]

    fails = sum(1 for r in rows if (r.get("status") or 0) >= 400)
    err503, _ = await _t(db._fetch_one(
        env,
        "SELECT COUNT(*) as c FROM usage_log "
        "WHERE ts > ? AND status = 503", since), 5.0)

    return {
        "window_hours": hours,
        "sample": len(lats),
        "p50_ms": pct(50),
        "p90_ms": pct(90),
        "p99_ms": pct(99),
        "avg_ms": int(sum(lats) / len(lats)) if lats else None,
        "error_rate": round(fails / len(rows), 4) if rows else 0.0,
        "pool_exhausted_503": (err503 or {}).get("c", 0) if isinstance(err503, dict) else 0,
    }


@app.get("/admin/stats/overview")
async def admin_stats_overview(request: Request):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    
    rows = await db._fetch_all(
        env, "SELECT * FROM usage_daily ORDER BY day DESC LIMIT 7")
    
    today_str = time.strftime("%Y-%m-%d", time.gmtime())
    
    # Check if today's summary is present in usage_daily
    has_today = any(r.get("day") == today_str for r in rows)
    if not has_today:
        today_ts = int(time.mktime(time.strptime(today_str, "%Y-%m-%d")))
        today_live = await db._fetch_one(
            env,
            "SELECT "
            "  COUNT(*) as total_requests, "
            "  SUM(CASE WHEN u.tier = 'free' OR u.tier IS NULL THEN 1 ELSE 0 END) as free_requests, "
            "  SUM(CASE WHEN u.tier = 'pro' THEN 1 ELSE 0 END) as pro_requests, "
            "  SUM(CASE WHEN l.cache_hit = 1 THEN 1 ELSE 0 END) as cache_hits, "
            "  SUM(CASE WHEN l.status >= 400 THEN 1 ELSE 0 END) as errors, "
            "  CAST(AVG(l.latency_ms) AS INTEGER) as avg_latency_ms "
            "FROM usage_log l "
            "LEFT JOIN users u ON l.user_id = u.firebase_uid "
            "WHERE l.ts >= ?1",
            today_ts,
        )
        today_row = {
            "day": today_str,
            "total_requests": (today_live or {}).get("total_requests") or 0,
            "free_requests": (today_live or {}).get("free_requests") or 0,
            "pro_requests": (today_live or {}).get("pro_requests") or 0,
            "cache_hits": (today_live or {}).get("cache_hits") or 0,
            "errors": (today_live or {}).get("errors") or 0,
            "avg_latency_ms": (today_live or {}).get("avg_latency_ms") or 0,
        }
        rows.insert(0, today_row)
        
    return {"days": rows}


@app.get("/admin/stats/usage")
async def admin_stats_usage(request: Request, days: int = 7):
    """Site-wide rollup chart (usage_daily), up to `days` back."""
    env = _bindings(request)
    if not await _super(request):
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


@app.get("/admin/users/paged")
async def admin_list_users_paged(request: Request, q: str | None = None,
                                 tier: str | None = None, page: int = 1,
                                 page_size: int = 25):
    """Server-side paginated + searchable user list for the dashboard."""
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    total = await db.count_users(env, q, tier)
    users = await db.list_users_paged(env, q, tier, page, page_size)
    return {
        "users": users,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size,
    }


@app.api_route("/admin/users/{uid}", methods=["PATCH", "POST", "PUT"])
async def admin_set_user(request: Request, uid: str):
    """Set a user's tier, active status, pro duration, and balance. Writes D1 and Firestore."""
    env = _bindings(request)
    auth = await _admin(request)
    if not auth:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)

    before = await db.get_user(env, uid) or {}
    details = {}

    tier = body.get("tier")
    if tier and str(tier).strip().lower() in ("free", "pro"):
        t_val = str(tier).strip().lower()
        if t_val == "free" and before.get("tier") == "pro":
            exp_raw = before.get("expires_at")
            if exp_raw and not body.get("force"):
                try:
                    exp_ts = int(exp_raw) if str(exp_raw).isdigit() else 0
                    if exp_ts > int(time.time()):
                        days_left = max(1, (exp_ts - int(time.time())) // 86400)
                        return JSONResponse(
                            {"error": f"Cannot downgrade to Free! User has an active Pro package running ({days_left} days remaining)."},
                            status_code=400
                        )
                except Exception:
                    pass
        try:
            await sync.set_user_tier(env, uid, t_val)
        except Exception:
            pass
        await db.set_user_tier(env, uid, t_val)
        details["tier"] = {"from": before.get("tier", "free"), "to": t_val}
        if t_val == "free":
            # Downgrade to free: clear any active Pro expiry so quota falls back to free.
            try:
                await env.DB.prepare(
                    "UPDATE users SET expires_at=NULL WHERE firebase_uid=?1").bind(uid).run()
            except Exception:
                pass

    # Pro duration handling (1 month / 15 days / 7 days / custom days)
    duration_days = body.get("duration_days") or body.get("durationDays")
    if duration_days and int(duration_days) > 0:
        days = int(duration_days)
        exp_ts = int(time.time()) + (days * 86400)
        try:
            await env.DB.prepare("UPDATE users SET expires_at=?1 WHERE firebase_uid=?2") \
                .bind(str(exp_ts), uid).run()
        except Exception:
            pass
        details["duration_days"] = days

    # Balance / Earnings handling (e.g. +499 taka)
    add_balance = body.get("add_balance") if "add_balance" in body else body.get("addBalance")
    amount = int(body.get("amount") or 499)
    if add_balance:
        cur_bal = int(before.get("balance") or 0)
        new_bal = cur_bal + amount
        try:
            await env.DB.prepare("UPDATE users SET balance=?1 WHERE firebase_uid=?2") \
                .bind(new_bal, uid).run()
        except Exception:
            pass
        details["added_balance"] = amount

    if "is_active" in body or "isActive" in body:
        val = body.get("is_active") if "is_active" in body else body.get("isActive")
        act_int = 1 if bool(val) else 0
        await db.set_user_status(env, uid, act_int)
        details["is_active"] = {"from": before.get("is_active", 1), "to": act_int}

    if details:
        await _log_sub_activity(env, auth, "set_user", uid, details)

    user = await db.get_user(env, uid)
    return {
        "uid": uid,
        "tier": (user or {}).get("tier", "free"),
        "is_active": (user or {}).get("is_active", 1),
        "balance": (user or {}).get("balance", 0),
        "expires_at": (user or {}).get("expires_at"),
    }


@app.get("/admin/subscriptions")
async def admin_list_subscriptions(request: Request):
    """List all subscription requests."""
    env = _bindings(request)
    if not await _admin(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    subs = await db.list_subscriptions(env)
    return {"subscriptions": subs}


@app.post("/admin/subscriptions/{sub_id}/approve")
async def admin_approve_subscription(request: Request, sub_id: str):
    """Approve a subscription request."""
    env = _bindings(request)
    auth = await _admin(request)
    if not auth:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    await db.update_subscription_status(env, sub_id, "approved")
    await _log_sub_activity(env, auth, "approve_subscription", sub_id, {"status": "approved"})
    return {"status": "ok", "id": sub_id}


@app.post("/admin/subscriptions/{sub_id}/reject")
async def admin_reject_subscription(request: Request, sub_id: str):
    """Reject a subscription request."""
    env = _bindings(request)
    auth = await _admin(request)
    if not auth:
        return JSONResponse({"error": "forbidden"}, status_code=403)

    await db.update_subscription_status(env, sub_id, "rejected")
    await _log_sub_activity(env, auth, "reject_subscription", sub_id, {"status": "rejected"})
    return {"status": "ok", "id": sub_id}



@app.get("/admin/plans")
async def admin_list_plans(request: Request):
    """List plan docs. Mirrors Firestore plan collection."""
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    rows = await db._fetch_all(
        env, "SELECT plan_id, daily_limit, price, plandetails FROM plans")
    return {"plans": rows}


@app.get("/admin/pricing")
async def admin_get_pricing(request: Request):
    """Get dynamic pricing configuration from plans."""
    env = _bindings(request)
    if not await _super(request):
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
    if not await _super(request):
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
            try:
                app.state.env = self.env
                app.state.flusher = db.BatchedFlusher(self.env)
                resp = await asgi.fetch(request, app)
                await app.state.flusher.aclose()
                return resp
            except BaseException as e:
                import traceback
                from js import Response
                tb = traceback.format_exc()
                body = json.dumps({"error": "internal", "type": type(e).__name__, "msg": str(e)[:500], "tb": tb[-1500:]}).encode()
                try:
                    await app.state.flusher.aclose()
                except BaseException:
                    pass
                return Response.new(body, {"status": 500, "headers": {"Content-Type": "application/json"}})

    return VRRouterEntrypoint


try:
    VRRouterEntrypoint = create_asgi_bridge()
except Exception:
    # local dev without workers-py: FastAPI runnable standalone
    @app.on_event("startup")
    async def _startup():
        pass
    VRRouterEntrypoint = None


@app.get("/admin/free-quota")
async def admin_get_free_quota(request: Request):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await db.get_free_quota(env)


@app.put("/admin/free-quota")
async def admin_set_free_quota(request: Request):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    try:
        limit = int(body.get("limit") or C.DEFAULT_FREE_DAILY_LIMIT)
    except (TypeError, ValueError):
        limit = C.DEFAULT_FREE_DAILY_LIMIT
    if limit < 1:
        return JSONResponse({"error": "limit_must_be_positive"}, status_code=400)
    cadence = str(body.get("cadence") or C.CADENCE_DEFAULT)
    if cadence not in (C.CADENCE_DAILY, C.CADENCE_NEVER, C.CADENCE_UNLIMITED):
        return JSONResponse({"error": "invalid_cadence"}, status_code=400)
    try:
        window_days = max(0, int(body.get("window_days") or 0))
    except (TypeError, ValueError):
        window_days = 0
    if cadence != C.CADENCE_DAILY:
        window_days = 0
    await db.set_free_quota(env, limit, cadence, window_days)
    return {"limit": limit, "cadence": cadence, "window_days": window_days}


@app.get("/admin/sub-admins")
async def admin_list_sub_admins(request: Request):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return {"sub_admins": await db.list_sub_admins(env)}


@app.get("/admin/sub-admins/activity/paged")
async def admin_list_sub_admin_activity_paged(
    request: Request,
    q: str | None = None,
    sub_admin: str | None = None,
    page: int = 1,
    page_size: int = 25,
):
    """Server-side paginated audit activity log of actions taken by sub-admins."""
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    total = await db.count_sub_admin_activity(env, q, sub_admin)
    items = await db.list_sub_admin_activity_paged(env, q, sub_admin, page, page_size)
    return {
        "activity": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@app.get("/admin/sub-admins/activity")
async def admin_list_sub_admin_activity(request: Request, limit: int = 100):
    """List recent sub-admin audit activity logs."""
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    limit = min(max(1, limit), 500)
    items = await db.list_sub_admin_activity(env, limit)
    return {"activity": items}



@app.post("/admin/sub-admins")
async def admin_add_sub_admin(request: Request):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if not (3 <= len(username) <= 64):
        return JSONResponse({"error": "invalid_username"}, status_code=400)
    if len(password) < 8:
        return JSONResponse({"error": "password_too_short"}, status_code=400)
    if await db.get_sub_admin_by_username(env, username):
        return JSONResponse({"error": "username_taken"}, status_code=409)
    sub_id = str(uuid.uuid4())
    await db.add_sub_admin(env, sub_id=sub_id, username=username,
                           pass_hash=admin_mod.hash_sub_password(password))
    return {"id": sub_id, "username": username, "is_active": 1}


@app.put("/admin/sub-admins/{sid}")
async def admin_update_sub_admin(request: Request, sid: str):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    sub = await db.get_sub_admin(env, sid)
    if not sub:
        return JSONResponse({"error": "not_found"}, status_code=404)
    fields = {}
    if "username" in body:
        username = str(body.get("username") or "").strip()
        if not (3 <= len(username) <= 64):
            return JSONResponse({"error": "invalid_username"}, status_code=400)
        existing = await db.get_sub_admin_by_username(env, username)
        if existing and existing["id"] != sid:
            return JSONResponse({"error": "username_taken"}, status_code=409)
        fields["username"] = username
    if "password" in body and body.get("password"):
        password = str(body["password"])
        if len(password) < 8:
            return JSONResponse({"error": "password_too_short"}, status_code=400)
        fields["pass_hash"] = admin_mod.hash_sub_password(password)
    if "is_active" in body:
        fields["is_active"] = 1 if bool(body.get("is_active")) else 0
    await db.update_sub_admin(env, sid, fields)
    row = await db.get_sub_admin(env, sid)
    return {"id": row["id"], "username": row["username"], "is_active": row["is_active"]}


@app.delete("/admin/sub-admins/{sid}")
async def admin_delete_sub_admin(request: Request, sid: str):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    if not await db.get_sub_admin(env, sid):
        return JSONResponse({"error": "not_found"}, status_code=404)
    await db.delete_sub_admin(env, sid)
    return {"deleted": sid}


@app.post("/admin/users/{uid}/quota/consume")
async def admin_consume_quota(request: Request, uid: str):
    """Admin-only: consume 1 quota for a user (same path as /v1/generate)."""
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        do = env.QUOTA.get(env.QUOTA.idFromName(uid))
        if do is None:
            return JSONResponse({"error": "QUOTA binding returned None"}, status_code=500)
        try:
            inc_res = await do.inc()
        except Exception as e:
            return JSONResponse({"error": f"do.inc failed: {type(e).__name__}: {e}"[:400]}, status_code=500)
        try:
            rem_res = await do.remaining()
        except Exception as e:
            return JSONResponse({"error": f"do.remaining failed: {type(e).__name__}: {e}"[:400]}, status_code=500)
        return {"uid": uid, "inc": inc_res, "remaining_rpc": rem_res}
    except Exception as e:
        return JSONResponse({"error": f"{type(e).__name__}: {e}"[:400]}, status_code=500)


@app.api_route("/admin/users/{uid}/reset-quota", methods=["POST", "PUT", "PATCH"])
async def admin_reset_user_quota(request: Request, uid: str):
    """Admin endpoint to reset a user's daily usage count to 0."""
    env = _bindings(request)
    auth = await _admin(request)
    if not auth:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    import time
    today_ts = int(time.time() // 86400) * 86400
    try:
        await env.DB.prepare("DELETE FROM usage_log WHERE user_id = ?1 AND ts >= ?2").bind(uid, today_ts).run()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    try:
        if hasattr(env, "QUOTA") and env.QUOTA:
            do = env.QUOTA.get(env.QUOTA.idFromName(uid))
            if do and hasattr(do, "reset"):
                await do.reset()
    except Exception:
        pass
    await _log_sub_activity(env, auth, "reset_quota", uid)
    return {"ok": True, "uid": uid, "reset_at": today_ts}


@app.api_route("/admin/users/{uid}/set-usage", methods=["POST", "PUT", "PATCH"])
async def admin_set_user_usage(request: Request, uid: str):
    """Admin endpoint to set today's usage count for a user."""
    env = _bindings(request)
    auth = await _admin(request)
    if not auth:
        return JSONResponse({"error": "forbidden"}, status_code=403)
    body = await _read_json(request) or {}
    usage_count = max(0, int(body.get("usage_count") or 0))
    import time
    today_ts = int(time.time() // 86400) * 86400
    try:
        await env.DB.prepare("DELETE FROM usage_log WHERE user_id = ?1 AND ts >= ?2").bind(uid, today_ts).run()
        for i in range(usage_count):
            await env.DB.prepare(
                "INSERT INTO usage_log (user_id, account_id, model, prompt_tokens, completion_tokens, cache_hit, latency_ms, status, ts) VALUES (?1, 'admin', 'admin', 0, 0, 0, 0, 200, ?2)"
            ).bind(uid, today_ts + i).run()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
    await _log_sub_activity(env, auth, "set_usage", uid, {"usage_count": usage_count})
    return {"ok": True, "uid": uid, "usage_count": usage_count}

# --------------------------------------------------------------------------- #
# Capacity alerts — hourly cron (wrangler [triggers]), deduped via KV.
# Sends to ALERT_WEBHOOK_URL (Cloudflare secret) when set; logs otherwise.
# --------------------------------------------------------------------------- #
async def _alert_post(url: str, text: str) -> None:
    try:
        from js import fetch as js_fetch, JSON as js_JSON
        init = js_JSON.parse(json.dumps({
            "method": "POST",
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"text": text, "content": text}),
        }))
        await js_fetch(url, init)
    except ImportError:
        import urllib.request
        req = urllib.request.Request(
            url, data=json.dumps({"text": text, "content": text}).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=8)


async def check_capacity_alerts(env) -> list[str]:
    """One alert per type per day (KV dedupe). Returns messages sent."""
    sent: list[str] = []
    day = time.strftime("%Y-%m-%d", time.gmtime())
    try:
        accounts, _ = await _t(db.list_enabled_accounts(env), 5.0)
        accounts = accounts or []
        capacity = sum(int(a.get("daily_limit") or 0) for a in accounts)
        today_start = int(time.time()) - (int(time.time()) % 86400)
        row, _ = await _t(db._fetch_one(
            env, "SELECT COUNT(*) as c FROM usage_log WHERE ts > ?", today_start), 5.0)
        used = (row or {}).get("c", 0) if isinstance(row, dict) else 0
    except Exception:
        return sent

    alerts: list[tuple[str, str]] = []
    if capacity > 0 and used / capacity >= 0.85:
        alerts.append((
            "capacity",
            f"⚠️ VidRank capacity at {100 * used // capacity}% ({used}/{capacity} today, "
            f"{len(accounts)} accounts). Add OpenRouter accounts now — pool will exhaust soon."))
    if len(accounts) <= 2:
        alerts.append((
            "pool",
            f"⚠️ VidRank pool has only {len(accounts)} enabled account(s). "
            f"One dead key = outage. Re-enable or add accounts."))
    try:
        err_row, _ = await _t(db._fetch_one(
            env, "SELECT COUNT(*) as c FROM usage_log WHERE ts > ? AND status = 503",
            int(time.time()) - 3600), 5.0)
        err503 = (err_row or {}).get("c", 0) if isinstance(err_row, dict) else 0
        if err503 >= 10:
            alerts.append((
                "errors",
                f"⚠️ VidRank served {err503} pool-exhausted 503s in the last hour. "
                f"Users are seeing generation failures — add accounts."))
    except Exception:
        pass

    for kind, msg in alerts:
        key = f"alert:{kind}:{day}"
        try:
            if await env.KV.get(key):
                continue
            await env.KV.put(key, "1", expiration_ttl=86400)
        except Exception:
            pass
        url = getattr(env, "ALERT_WEBHOOK_URL", "") or ""
        if url:
            await _alert_post(url, msg)
        print(f"[alert] {msg}", file=sys.stderr, flush=True)
        sent.append(msg)
    return sent
