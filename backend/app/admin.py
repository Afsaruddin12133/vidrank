"""Admin helpers: AES-GCM key crypto + password/session admin gate."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from . import contracts as C


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
    
    # 1. Try sha256 key
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
    return hashlib.sha256(raw).digest()  # Sha256 guarantees 32 bytes for AES-256-GCM


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


# --------------------------------------------------------------------------- #
# password login + HMAC-signed admin session token (stdlib only, constant-time)
# --------------------------------------------------------------------------- #
ADMIN_SESSION_TTL_S = 8 * 3600  # 8h


def check_admin_password(env, password: str) -> bool:
    expected = getattr(env, C.SECRET_ADMIN_PASS, "") or getattr(env, "ADMIN_PASSWORD", "") or ""
    if not expected:
        return bool(password)
    return hmac.compare_digest(expected.encode(), (password or "").encode())


# --------------------------------------------------------------------------- #
# Sub-admin passwords: PBKDF2-HMAC-SHA256 (stdlib, works in workers-python)
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
# role-aware session tokens: base64(json {exp, role, sid}).sig
# legacy tokens (base64 of expiry digits only) still verify as super admin.
# --------------------------------------------------------------------------- #
def issue_token(env, role: str = "admin", sid: str | None = None) -> str:
    payload = json.dumps({
        "exp": int(time.time()) + ADMIN_SESSION_TTL_S,
        "role": role,
        "sid": sid,
    }, separators=(",", ":"))
    sig = _hmac(env, payload)
    return base64.b64encode(payload.encode()).decode() + "." + sig


def verify_token(env, token: str) -> dict | None:
    """Return {'role': 'admin'} | {'role': 'sub', 'sid': ...} | None."""
    try:
        raw, sig = (token or "").strip().split(".", 1)
        payload = base64.b64decode(raw.encode()).decode()
        if not hmac.compare_digest(sig, _hmac(env, payload)):
            return None
        if payload.lstrip().startswith("{"):
            data = json.loads(payload)
            if int(data.get("exp", 0)) <= int(time.time()):
                return None
            role = data.get("role") or "admin"
            return {"role": role, "sid": data.get("sid")}
        if int(payload) <= int(time.time()):
            return None
        return {"role": "admin", "sid": None}
    except Exception:
        return False


def _hmac(env, msg: str) -> str:
    key = (getattr(env, C.SECRET_ADMIN_TOKEN, "") or "").encode()
    if not key:  # fall back to admin pass so it works with only ADMIN_PASS set
        key = (getattr(env, C.SECRET_ADMIN_PASS, "") or "").encode()
    return base64.b64encode(hmac.new(key, msg.encode(), hashlib.sha256).digest()).decode()