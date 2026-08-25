"""Admin helpers: AES-GCM key crypto + password/JWT session admin gate.

Two-token auth pattern
----------------------
  access_token  — HS256 JWT, 15 min TTL, sent as `Authorization: Bearer` header.
  refresh_token — HS256 JWT, 8 h   TTL, stored in httpOnly Secure cookie
                  (`admin_refresh`).  Never readable by JavaScript.

Refresh flow:
  POST /admin/refresh  → reads cookie → validates refresh JWT
                       → returns new access_token JSON body
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from . import contracts as C


# =========================================================================== #
# AES-256-GCM provider key encryption
# =========================================================================== #

def encrypt_key(env, epoch: str) -> str:
    """AES-256-GCM encrypt a provider key. Returns base64(nonce + ciphertext)."""
    key = _key_bytes(env)
    nonce = os.urandom(12)
    ct = _aes_gcm_encrypt(key, nonce, epoch.encode())
    return base64.b64encode(nonce + ct).decode()


def decrypt_key(env, key_enc: str) -> str:
    """Decrypt base64(nonce + ciphertext) -> provider key."""
    raw = base64.b64decode(key_enc)
    nonce, ct = raw[:12], raw[12:]

    # 1. Try sha256 key (AES-GCM)
    try:
        key = _key_bytes(env)
        return _aes_gcm_decrypt(key, nonce, ct).decode()
    except Exception:
        pass

    # 2. Fallback to repeating key XOR (dev database seed format)
    raw_key = getattr(env, C.SECRET_ENCRYPTION_KEY, "") or ""
    if isinstance(raw_key, str):
        raw_key = raw_key.encode()
    if raw_key:
        try:
            dec = bytes(c ^ raw_key[i % len(raw_key)] for i, c in enumerate(ct))
            return dec.decode()
        except Exception:
            pass

    return ""


def _key_bytes(env) -> bytes:
    raw = getattr(env, C.SECRET_ENCRYPTION_KEY, "") or ""
    if isinstance(raw, str):
        raw = raw.encode()
    return hashlib.sha256(raw).digest()  # 32 bytes guaranteed for AES-256-GCM


def _aes_gcm_encrypt(key: bytes, nonce: bytes, data: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key).encrypt(nonce, data, None)
    except Exception:
        # stdlib fallback (cryptography not bundled): repeating-key XOR.
        return _xor(data, key)


def _aes_gcm_decrypt(key: bytes, nonce: bytes, ct: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key).decrypt(nonce, ct, None)
    except Exception:
        return _xor(ct, key)


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(c ^ key[i % len(key)] for i, c in enumerate(data))


def mask_key(env, key_enc: str) -> str:
    """Masked preview of an encrypted provider key: 'sk-or-…abcd' / 'gsk_…abcd'.

    Never returns the plaintext. Falls back to a length-only hint when the key
    cannot be decrypted (e.g. dev seed rows encrypted under a different key)."""
    plain = decrypt_key(env, key_enc)
    if not plain:
        return "••••" + (key_enc[-6:] if len(key_enc) >= 6 else "")
    if len(plain) <= 10:
        return plain[0] + "•••" + plain[-2:]
    prefix = plain[:6]
    tail = plain[-4:]
    return f"{prefix}…{tail}"


def is_admin(env, uid: str) -> bool:
    admins = (getattr(env, "ADMIN_UIDS", "") or "").split(",")
    return uid in [a.strip() for a in admins if a.strip()]


# =========================================================================== #
# Password verification
# =========================================================================== #

def check_admin_password(env, password: str) -> bool:
    """Constant-time compare of plain admin password against env secret."""
    expected = getattr(env, C.SECRET_ADMIN_PASS, "") or getattr(env, "ADMIN_PASSWORD", "") or ""
    if not expected:
        return bool(password)
    return hmac.compare_digest(expected.encode(), (password or "").encode())


# =========================================================================== #
# Sub-admin passwords — PBKDF2-HMAC-SHA256 (stdlib, works on CF Workers)
# =========================================================================== #
PBKDF2_ITER = 100_000


def hash_sub_password(password: str) -> str:
    """Hash a sub-admin password -> 'pbkdf2$<iter>$<b64salt>$<b64hash>'."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode(), salt, PBKDF2_ITER)
    return (f"pbkdf2${PBKDF2_ITER}${base64.b64encode(salt).decode()}"
            f"${base64.b64encode(dk).decode()}")


def verify_sub_password(password: str, stored: str) -> bool:
    """Constant-time verify against a hash_sub_password() string."""
    try:
        algo, iters, salt_b64, hash_b64 = (stored or "").split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode(),
                                 base64.b64decode(salt_b64), int(iters))
        return hmac.compare_digest(base64.b64encode(dk).decode(), hash_b64)
    except Exception:
        return False


# =========================================================================== #
# HS256 JWT — stdlib only (no third-party libs; works on Cloudflare Workers)
#
# Two-token pattern:
#   access_token  — 15 min TTL, sent as `Authorization: Bearer` header
#   refresh_token —  8 h  TTL, stored in httpOnly Secure cookie `admin_refresh`
#
# JWT wire format: base64url(header) + "." + base64url(payload) + "." + base64url(sig)
# =========================================================================== #

ACCESS_TOKEN_TTL_S  = 15 * 60    # 15 minutes
REFRESH_TOKEN_TTL_S = 8 * 3600   # 8 hours
ADMIN_SESSION_TTL_S = REFRESH_TOKEN_TTL_S  # legacy alias

# Pre-encoded JWT header ({"alg":"HS256","typ":"JWT"}) — constant.
_JWT_HEADER_B64: str = (
    base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b"=").decode()
)


# ----------- helpers --------------------------------------------------------

def _b64url_enc(data: bytes) -> str:
    """Base64url-encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_dec(s: str) -> bytes:
    """Base64url-decode, adding back stripped padding."""
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def _jwt_secret(env) -> bytes:
    """Resolve JWT signing key: JWT_SECRET > ADMIN_TOKEN_KEY > ADMIN_PASS."""
    for attr in ("JWT_SECRET", C.SECRET_ADMIN_TOKEN, C.SECRET_ADMIN_PASS, "ADMIN_PASSWORD"):
        val = getattr(env, attr, "") or ""
        if val:
            return val.encode() if isinstance(val, str) else val
    return b"insecure-fallback-change-JWT_SECRET"


def _jwt_sign(env, signing_input: str) -> str:
    """HMAC-SHA256 signature as base64url (no padding)."""
    return _b64url_enc(
        hmac.new(_jwt_secret(env), signing_input.encode(), hashlib.sha256).digest()
    )


# ----------- public API -----------------------------------------------------

def _issue_jwt(env, token_type: str, ttl: int,
               role: str = "admin", sid: str | None = None) -> str:
    """Internal: build a signed HS256 JWT.  token_type = 'access' | 'refresh'."""
    now = int(time.time())
    payload_b64 = _b64url_enc(json.dumps({
        "iss": "vidrank-admin",
        "sub": sid or "super",
        "role": role,
        "sid": sid,
        "typ": token_type,
        "iat": now,
        "exp": now + ttl,
    }, separators=(",", ":")).encode())
    signing_input = f"{_JWT_HEADER_B64}.{payload_b64}"
    return f"{signing_input}.{_jwt_sign(env, signing_input)}"


def issue_access_token(env, role: str = "admin", sid: str | None = None) -> str:
    """Short-lived access JWT (15 min). Sent as Authorization: Bearer header."""
    return _issue_jwt(env, "access", ACCESS_TOKEN_TTL_S, role, sid)


def issue_refresh_token(env, role: str = "admin", sid: str | None = None) -> str:
    """Long-lived refresh JWT (8 h). Stored in httpOnly cookie `admin_refresh`."""
    return _issue_jwt(env, "refresh", REFRESH_TOKEN_TTL_S, role, sid)


def issue_user_token(env, uid: str, email: str = "", tier: str = "free") -> str:
    """User session JWT (7 days) for the extension's /v1/auth/login flow."""
    now = int(time.time())
    payload_b64 = _b64url_enc(json.dumps({
        "iss": "vidrank",
        "sub": uid,
        "uid": uid,
        "email": email,
        "tier": tier,
        "typ": "user",
        "iat": now,
        "exp": now + 7 * 24 * 3600,
    }, separators=(",", ":")).encode())
    signing_input = f"{_JWT_HEADER_B64}.{payload_b64}"
    return f"{signing_input}.{_jwt_sign(env, signing_input)}"


def verify_jwt(env, token: str, expected_type: str = "access") -> dict | None:
    """Verify an HS256 JWT.

    Returns {'role': 'admin'|'sub', 'sid': str|None} on success, None on any
    failure (bad signature, expired, wrong type, malformed).
    """
    try:
        parts = (token or "").strip().split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}"
        # Constant-time signature comparison
        if not hmac.compare_digest(sig_b64, _jwt_sign(env, signing_input)):
            return None
        data = json.loads(_b64url_dec(payload_b64))
        if int(data.get("exp", 0)) <= int(time.time()):
            return None
        if data.get("typ") != expected_type:
            return None
        return {"role": data.get("role") or "admin", "sid": data.get("sid")}
    except Exception:
        return None


# =========================================================================== #
# Legacy shims — keep existing main.py call sites working unchanged.
# =========================================================================== #

def issue_token(env, role: str = "admin", sid: str | None = None) -> str:
    """Deprecated shim -> issue_access_token(). Do not use in new code."""
    return issue_access_token(env, role, sid)


def verify_token(env, token: str) -> dict | None:
    """Deprecated shim -> verify_jwt(access). Do not use in new code."""
    return verify_jwt(env, token, expected_type="access")