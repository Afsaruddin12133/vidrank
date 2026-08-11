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
_ALLOW_HEADERS = ["Authorization", "Content-Type"]


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
                headers.append((b"vary", b"Origin"))
                headers.append(
                    (
                        b"access-control-expose-headers",
                        b"X-Request-Id",
                    )
                )
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
    code = "token_expired" if isinstance(e, firebase.TokenExpired) else "unauthorized"
    return JSONResponse({"error": code}, status_code=401)


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
                print(f"[SERVER MIDDLEWARE] OUTGOING RESPONSE: {method} {path} => Status: {message['status']}\n", file=sys.stderr, flush=True)
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
    if user and user.get("is_active") == 0:
        return JSONResponse(
            {"error": "account_suspended", "message": "Account suspended by administrator"},
            status_code=403,
        )
    tier = db.get_effective_tier(user) if user else C.TIER_FREE

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

    # 3) quota check (free: dailyLimit; pro: unlimited)
    if tier != C.TIER_PRO:
        u_dict, _ = await _usage_for(env, uid, tier)
        if u_dict.get("remaining", 1) <= 0:
            resets = max(0, int(((int(time.time()) // 86400) + 1) * 86400 - time.time()))
            return JSONResponse(
                {"error": "quota_exceeded",
                 "quota_remaining": 0,
                 "resets_in_seconds": resets},
                status_code=429,
            )

    # 4) route to the pool (with fallback inside router)
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
        return JSONResponse({"error": "generation_failed"}, status_code=502)

    # 6) consume quota only after a successful generation
    await _consume_quota(env, uid)

    tags, desc = parsed["tags"], parsed["description"]
    await cache.store_exact(env, key, json.dumps({"tags": tags, "description": desc}))
    if C.TIER_FREE == tier:
        await cache.store_semantic(env, uid, prompts.GENERATE_MODEL, sem_key_text,
                                   json.dumps({"tags": tags, "description": desc}))

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
        do = env.QUOTA.get(env.QUOTA.idFromName(uid))
        if do is not None:
            await do.inc()
    except Exception:
        pass  # Silently fail - optimistic frontend will handle it


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
        return {
            "uid": uid,
            "email": claims.get("email") or (user or {}).get("email"),
            "tier": tier,
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
# admin API
# --------------------------------------------------------------------------- #
@app.api_route("/admin/login", methods=["POST", "GET", "PUT", "PATCH"])
async def admin_login(request: Request):
    """Login. Super admin: {password}. Sub-admin: {username, password}."""
    env = _bindings(request)
    if request.method == "GET":
        return JSONResponse({"status": "login_endpoint_active"})
    body = await _read_json(request)
    if body is None:
        return JSONResponse({"error": "bad_request"}, status_code=400)
    username = str(body.get("username") or "").strip()
    password = str(body.get("password") or "")
    if username:
        sub = await db.get_sub_admin_by_username(env, username)
        if not sub or not sub.get("is_active"):
            return JSONResponse({"error": "invalid_credentials"}, status_code=401)
        if not admin_mod.verify_sub_password(password, sub.get("pass_hash") or ""):
            return JSONResponse({"error": "invalid_credentials"}, status_code=401)
        return {
            "token": admin_mod.issue_token(env, role="sub", sid=sub["id"]),
            "expires_in_s": admin_mod.ADMIN_SESSION_TTL_S,
            "role": "sub",
            "username": sub["username"],
        }
    if not admin_mod.check_admin_password(env, password):
        return JSONResponse({"error": "invalid_credentials"}, status_code=401)
    return {
        "token": admin_mod.issue_token(env),
        "expires_in_s": admin_mod.ADMIN_SESSION_TTL_S,
        "role": "admin",
    }


async def _admin(request: Request) -> dict | None:
    env = _bindings(request)
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return admin_mod.verify_token(env, token)


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
    accounts = await db.list_accounts(env)
    for a in accounts:
        a["key_preview"] = admin_mod.mask_key(env, a.pop("key_enc", "")) if a.get("key_enc") else ""
    return {"accounts": accounts}


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
    """Server-side paginated per-account usage rollup chart data."""
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    days = min(max(days, 1), 90)
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    total = await db.count_accounts(env, q, provider)
    accounts = await db.list_accounts_paged(env, q, provider, page, page_size)

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


@app.get("/admin/accounts/health")
async def admin_accounts_health(request: Request):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    out = {}
    for a in await db.list_enabled_accounts(env):
        try:
            out[a["id"]] = await env.RATESTATE.get(env.RATESTATE.idFromName(a["id"])).get_health()
        except Exception:
            out[a["id"]] = {"health": None}
    return {"health": out}


@app.get("/admin/accounts/{account_id}/usage")
async def admin_account_usage(request: Request, account_id: str):
    env = _bindings(request)
    if not await _super(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    try:
        acc = await db.get_account(env, account_id)
    except Exception:
        acc = None
    try:
        live = await env.RATESTATE.get(env.RATESTATE.idFromName(account_id)).get_live()
    except Exception:
        live = None
    return {"live": live, "limit": (acc or {}).get("daily_limit"),
            "rpm_limit": (acc or {}).get("rpm_limit")}


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
    """Set a user's tier or active status. Writes D1 and Firestore."""
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
        try:
            await sync.set_user_tier(env, uid, t_val)
        except Exception:
            pass
        await db.set_user_tier(env, uid, t_val)
        details["tier"] = {"from": before.get("tier", "free"), "to": t_val}

    if "is_active" in body or "isActive" in body:
        val = body.get("is_active") if "is_active" in body else body.get("isActive")
        act_int = 1 if bool(val) else 0
        await db.set_user_status(env, uid, act_int)
        details["is_active"] = {"from": before.get("is_active", 1), "to": act_int}

    if details:
        await _log_sub_activity(env, auth, "set_user", uid, details)

    user = await db.get_user(env, uid)
    return {"uid": uid, "tier": (user or {}).get("tier", "free"), "is_active": (user or {}).get("is_active", 1)}


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