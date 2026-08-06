"""Firestore -> D1 scheduled sync (plan/DATABASE.md, plan/TIERS.md).

Cron (5 min): upsert `plans` (dailyLimit from Firestore `plan` docs) and
`users` mirror (uid, email, tier, isActive). Tier flips land <= 5 min without
redeploy. Firestore is the source of truth.

Firestore accessed via REST (REST API, googleapis) using a service-account
token; if FIRESTORE env vars are absent, sync no-ops gracefully.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.error

from . import contracts as C
from . import db


def _firestore_base(env) -> str | None:
    url = getattr(env, "FIRESTORE_DB_URL", "") or ""
    return url or None


async def _rest_get(env, path: str) -> dict | None:
    base = _firestore_base(env)
    if not base:
        return None
    try:
        req = urllib.request.Request(f"{base}/{path}", headers={"User-Agent": "vidrank"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None


async def sync_plans(env) -> None:
    """Upsert plans into D1 from Firestore `plan` docs."""
    base = _firestore_base(env)
    if not base:
        return  # not configured; graceful no-op
    now = int(time.time())
    for plan_id in (C.TIER_FREE, C.TIER_PRO):
        doc = await _rest_get(env, f"documents/plan/{plan_id}")
        if not doc or "fields" not in doc:
            continue
        fields = doc["fields"]
        dl = fields.get("dailyLimit", {}).get("integerValue")
        daily_limit = int(dl) if dl else None
        price = _fs(fields, "price", "price", "int")
        details = _fs(fields, "plandetails", "plandetails", "string")
        try:
            await env.DB.prepare(
                "INSERT OR REPLACE INTO plans (plan_id, daily_limit, synced_at, price, plandetails) "
                "VALUES (?,?,?,?,?)"
            ).bind(plan_id, daily_limit, now, price, details).run()
        except Exception:
            pass


def _fs(fields: dict, name: str, key: str, kind: str):
    """Read a Firestore field, returning None when absent."""
    v = fields.get(key, {})
    if kind == "string":
        return v.get("stringValue")
    if kind == "int":
        iv = v.get("integerValue")
        return int(iv) if iv else None
    if kind == "bool":
        return int(v.get("booleanValue", True))
    return None


async def sync_users(env) -> None:
    """Upsert users mirror into D1 from Firestore `users` collection."""
    base = _firestore_base(env)
    if not base:
        return
    now = int(time.time())
    doc = await _rest_get(env, "documents/users?pageSize=500")
    if not doc or "documents" not in doc:
        return
    for d in doc["documents"]:
        name = d.get("name", "")
        uid = name.rsplit("/", 1)[-1]
        fields = d.get("fields", {})
        email = fields.get("email", {}).get("stringValue", "")
        plan = fields.get("plan", {}).get("stringValue", C.TIER_FREE)
        active = int(fields.get("isActive", {}).get("booleanValue", True))
        balance = _fs(fields, "balance", "balance", "int")
        sub_id = _fs(fields, "subscriptionId", "subscriptionId", "string")
        expires = _fs(fields, "expiresAt", "expiresAt", "string")
        referred = _fs(fields, "referredBy", "referredBy", "string")
        referred_sub = _fs(fields, "referredBySubId", "referredBySubId", "string")
        usage = _fs(fields, "usageCount", "usageCount", "int")
        reset = _fs(fields, "lastUsageReset", "lastUsageReset", "int")
        display_name = _fs(fields, "name", "name", "string") or ""
        photo = _fs(fields, "photoUrl", "photoUrl", "string")
        try:
            await env.DB.prepare(
                "INSERT OR REPLACE INTO users (firebase_uid, email, tier, is_active, synced_at, "
                "balance, subscription_id, expires_at, referred_by, usage_count, last_usage_reset, "
                "name, photo_url, referred_by_sub_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            ).bind(uid, email, plan, active, now, balance, sub_id, expires, referred,
                   usage or 0, reset, display_name, photo, referred_sub).run()
        except Exception:
            pass


async def sync_one_user(env, uid: str) -> dict | None:
    """Upsert a single Firestore user doc into D1; None when Firestore absent."""
    base = _firestore_base(env)
    if not base:
        return None
    doc = await _rest_get(env, f"documents/users/{uid}")
    if not doc or "fields" not in doc:
        return None
    fields = doc["fields"]
    user = {
        "firebase_uid": uid,
        "email": fields.get("email", {}).get("stringValue", ""),
        "tier": fields.get("plan", {}).get("stringValue", C.TIER_FREE),
        "is_active": int(fields.get("isActive", {}).get("booleanValue", True)),
        "synced_at": int(time.time()),
        "balance": _fs(fields, "balance", "balance", "int"),
        "subscription_id": _fs(fields, "subscriptionId", "subscriptionId", "string"),
        "expires_at": _fs(fields, "expiresAt", "expiresAt", "string"),
        "referred_by": _fs(fields, "referredBy", "referredBy", "string"),
        "referred_by_sub_id": _fs(fields, "referredBySubId", "referredBySubId", "string"),
        "usage_count": _fs(fields, "usageCount", "usageCount", "int") or 0,
        "last_usage_reset": _fs(fields, "lastUsageReset", "lastUsageReset", "int"),
        "name": _fs(fields, "name", "name", "string") or "",
        "photo_url": _fs(fields, "photoUrl", "photoUrl", "string"),
    }
    await db.upsert_user(env, user)
    return user


async def set_user_tier(env, uid: str, tier: str) -> None:
    """Admin PATCH /admin/users/{id}: write users.plan in Firestore."""
    base = _firestore_base(env)
    if not base:
        raise RuntimeError("Firestore not configured")
    url = f"{base}/documents/users/{uid}?updateMask.fieldPaths=plan"
    body = json.dumps({"fields": {"plan": {"stringValue": tier}}}).encode()
    req = urllib.request.Request(
        url, data=body, method="PATCH",
        headers={"Content-Type": "application/json", "User-Agent": "vidrank"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"firestore update failed: {resp.status}")


async def update_plan_limit(env, plan_id: str, daily_limit: int | None) -> None:
    """Admin PATCH /admin/plans: write plan doc in Firestore (synced to D1)."""
    base = _firestore_base(env)
    if not base:
        raise RuntimeError("Firestore not configured")
    url = f"{base}/documents/plan/{plan_id}?updateMask.fieldPaths=dailyLimit"
    value = ({"integerValue": str(daily_limit)} if daily_limit is not None
             else {"nullValue": None})
    body = json.dumps({"fields": {"dailyLimit": value}}).encode()
    req = urllib.request.Request(
        url, data=body, method="PATCH",
        headers={"Content-Type": "application/json", "User-Agent": "vidrank"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"firestore update failed: {resp.status}")