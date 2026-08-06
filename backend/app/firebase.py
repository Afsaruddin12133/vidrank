"""Firebase ID-token verification using official firebase_admin SDK."""
from __future__ import annotations

import os
import sys
import firebase_admin
from firebase_admin import auth, credentials


class AuthError(Exception):
    pass


class TokenExpired(AuthError):
    """Raised when the Firebase ID token is expired/revoked (client must refresh)."""
    pass


_app = None


def _get_firebase_app():
    global _app
    if _app is None and not firebase_admin._apps:
        # Search for auth.json in backend/ or scripts/
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cert_path = os.path.join(base_dir, "auth.json")
        if not os.path.exists(cert_path):
            cert_path = os.path.join(os.path.dirname(base_dir), "scripts", "auth.json")

        if os.path.exists(cert_path):
            cred = credentials.Certificate(cert_path)
            _app = firebase_admin.initialize_app(cred)
            print(f"[firebase] Initialized Firebase Admin SDK with key: {cert_path}", file=sys.stderr, flush=True)
        else:
            _app = firebase_admin.initialize_app()
            print("[firebase] Initialized Firebase Admin SDK with default credentials", file=sys.stderr, flush=True)
    return _app


async def verify_token(token: str, env=None) -> dict:
    """Verify Firebase ID token using firebase_admin SDK."""
    if not token:
        raise AuthError("missing token")

    _get_firebase_app()

    try:
        claims = auth.verify_id_token(token)
        print(f"[auth-success] Verified token for {claims.get('email')} (uid: {claims.get('uid')})", file=sys.stderr, flush=True)
        return claims
    except (auth.ExpiredIdTokenError, auth.RevokedIdTokenError) as e:
        print(f"[auth-expired] {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        raise TokenExpired(str(e)) from e
    except Exception as e:
        print(f"[auth-debug] Firebase Admin verification failed: {e}", file=sys.stderr, flush=True)
        raise AuthError(str(e)) from e


async def revoke_session(env, uid: str) -> None:
    """Revoke user refresh tokens using Firebase Admin SDK."""
    try:
        _get_firebase_app()
        auth.revoke_refresh_tokens(uid)
    except Exception as e:
        print(f"[auth-debug] Revoke failed: {e}", file=sys.stderr, flush=True)