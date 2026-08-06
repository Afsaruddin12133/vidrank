"""Firebase ID-token verification client — calls the vidrank-auth service
worker over a service binding instead of bundling the firebase-admin SDK.

The heavy firebase_admin package lives in the separate `auth-worker/` project
so the main API worker stays under Cloudflare's free-plan 3 MiB size cap.

Interface is unchanged from the old in-process implementation:
    verify_token(token, env) -> dict   # raises AuthError / TokenExpired
    revoke_session(env, uid) -> None
"""
from __future__ import annotations

import json


class AuthError(Exception):
    pass


class TokenExpired(AuthError):
    """Raised when the Firebase ID token is expired/revoked (client must refresh)."""
    pass


# Path used when calling the auth service over the AUTH service binding.
_AUTH_URL = "https://vidrank-auth/verify"


async def _call_auth(env, payload: dict) -> dict:
    if env is None or not hasattr(env, "AUTH"):
        raise AuthError("auth service binding unavailable")
    resp = await env.AUTH.fetch(
        _AUTH_URL,
        method="POST",
        body=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )
    text = await resp.text()
    try:
        data = json.loads(text)
    except Exception:
        print(f"[auth] bad response from auth service: {text[:200]}", flush=True)
        raise AuthError("auth service returned invalid response")
    return data


async def verify_token(token: str, env=None) -> dict:
    """Verify Firebase ID token by calling the vidrank-auth service worker."""
    if not token:
        raise AuthError("missing token")

    data = await _call_auth(env, {"token": token})

    if data.get("ok"):
        claims = data.get("claims") or {}
        print(f"[auth-success] Verified token for {claims.get('email')} (uid: {claims.get('uid')})", flush=True)
        return claims

    code = data.get("code")
    if code == "token_expired":
        print(f"[auth-expired] {data.get('detail')}", flush=True)
        raise TokenExpired(data.get("detail") or "token expired")
    print(f"[auth-debug] Auth service rejected token: {data.get('detail')}", flush=True)
    raise AuthError(data.get("detail") or "unauthorized")


async def revoke_session(env, uid: str) -> None:
    """Revoke user refresh tokens (delegated to the auth service worker)."""
    try:
        await _call_auth(env, {"action": "revoke", "uid": uid})
    except Exception as e:
        print(f"[auth-debug] Revoke failed: {e}", flush=True)