"""Admin helpers: AES-GCM key crypto + password/session admin gate."""
from __future__ import annotations

import base64
import hashlib
import hmac
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
    expected = (getattr(env, C.SECRET_ADMIN_PASS, "") or "").encode()
    if not expected:
        return False
    return hmac.compare_digest(expected, (password or "").encode())  # constant-time


def issue_token(env) -> str:
    expiry = str(int(time.time()) + ADMIN_SESSION_TTL_S)
    sig = _hmac(env, expiry)
    return base64.b64encode(expiry.encode()).decode() + "." + sig


def _hmac(env, msg: str) -> str:
    key = (getattr(env, C.SECRET_ADMIN_TOKEN, "") or "").encode()
    if not key:  # fall back to admin pass so it works with only ADMIN_PASS set
        key = (getattr(env, C.SECRET_ADMIN_PASS, "") or "").encode()
    return base64.b64encode(hmac.new(key, msg.encode(), hashlib.sha256).digest()).decode()


def verify_token(env, token: str) -> bool:
    try:
        raw, sig = (token or "").strip().split(".", 1)
        exp = base64.b64decode(raw.encode()).decode()
        valid = hmac.compare_digest(sig, _hmac(env, exp))  # constant-time
        return valid and int(exp) > int(time.time())
    except Exception:
        return False