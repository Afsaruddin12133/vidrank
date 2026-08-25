# DEPLOY NOTE — READ BEFORE EVERY BACKEND DEPLOY (learned the hard way)

## The ONLY way to deploy this worker
```bash
cd /Users/macm1/Desktop/vidrank/backend
# CRITICAL: the deploy dir must be duplicate-free or you blow the 3 MiB limit.
# Run these THREE cleanup steps every time:
mv .venv /tmp/vidrank_venv_$(date +%s)              # 90M macOS venv — MUST be out
rm -rf .venv-workers/lib                           # redundant macOS duplicate
rm -rf python_modules                              # forbidden manually-populated dir (see #1)
pywrangler deploy
mv /tmp/vidrank_venv_* .venv                       # restore for the local dev server
```

`pywrangler` (from `uv tool install workers-py`) is REQUIRED. It builds WASM/Pyodide-compatible
wheels into `.venv-workers/pyodide-venv`. Plain `wrangler deploy` or `npx wrangler deploy` WILL
FAIL with `ModuleNotFoundError: No module named 'fastapi'` (10021) — wrangler does NOT resolve
pyproject.toml deps itself.

## Never do these again
1. **NEVER manually copy packages from `.venv_bak`/`.venv` into `python_modules`.** They are
   macOS (CPython) builds — they CANNOT run on Cloudflare's WASM runtime. Result: confusing
   import errors (`annotated_doc`, `pydantic_core`, `fastapi`, …) one at a time.
   On Aug 12 this dir silently grew back to 8.9M with a 4 MB `pydantic_core/_pydantic_core.so`
   duplicate → 10027 "exceeded 3 MiB". `rm -rf python_modules` is now part of every deploy.
2. **NEVER create a `requirements.txt`** — dependency resolution is pyproject.toml-based,
   done by pywrangler (uv).
3. **NEVER leave `.venv`, `.venv_bak`, or a duplicate `.venv-workers/lib` in the deploy dir.**
   Wrangler bundles what's in the folder → 10027 "exceeded the size limit of 3 MiB".
   The successful bundle was ~4.4MB duplicate-free = under the 3MiB (gzip) free limit.
4. There are NO WASM wheels on PyPI (`pip`/`uv` won't find pydantic_core for wasm32) — do not
   try `pip download --platform emscripten...`; pywrangler's configured resolver handles it.
5. **`pydantic_core>=2.27` is BROKEN on Cloudflare Workers Python runtime** (Aug 12).
   Import-time `os.urandom` call isn't covered by `_cloudflare/entropy_import_context.py`'s
   `pydantic_core_context` → `RuntimeError: 1 unexpected leftover getentropy calls` (10021).
   **Pin to `<2.27` in pyproject.toml.** Already done: `dependencies = ["fastapi", "pydantic-core<2.27"]`.

## Verification after deploy (all must be 200)
```bash
curl -s https://vidrank-backend.fahad288ali.workers.dev/healthz          # {"ok":true}
# Login now returns JWT (NOT the old HMAC `token` field — see Aug 12 deploy note below):
TOKEN=$(curl -s -X POST https://vidrank-backend.fahad288ali.workers.dev/admin/login \
  -H "Content-Type: application/json" -H "User-Agent: Mozilla/5.0" \
  -d '{"password":"#admin23CHECK"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -s https://vidrank-backend.fahad288ali.workers.dev/admin/users -H "Authorization: Bearer $TOKEN"
curl -s https://vidrank-backend.fahad288ali.workers.dev/admin/sub-admins -H "Authorization: Bearer $TOKEN"
curl -s https://vidrank-backend.fahad288ali.workers.dev/admin/sub-admins/activity -H "Authorization: Bearer $TOKEN"
```
Always send a browser UA (`User-Agent: Mozilla/5.0 ...`) — Cloudflare edge 403s `Python-urllib`.

## Other facts
- Account: Fahad288ali@gmail.com / Account ID 888ad088a0b226524650478393ad1561
- Live worker: https://vidrank-backend.fahad288ali.workers.dev
  - **Aug 12**: Version ID `55950f44-ded4-4848-b1ea-1df381f16e49` — sub-admin activity log + Dashboard gating for subs
  - Aug 8: Version ID `efe2fe5b-f400-47b5-84f7-abb9d956820b` — sub-admin management
- Frontend (Pages): https://vidrank-dashboard.pages.dev
  - **Aug 12**: Deploy `5e4d54c8.vidrank-dashboard.pages.dev` — activity log UI in Sub Admins page + Dashboard gating
- Admin password: `#admin23CHECK` → POST /admin/login → Bearer JWT (expires 15 min, `access_token_ttl_s`)

## Aug 12 deploy — what shipped and the three fixes

**Shipped:**
- **Sub-admin activity log** (the feature the user asked for: "which people they gave subscription … activity … saved on database … view in super admin portal"). Every sub-admin action on `/admin/users/{uid}` (tier change, activate/suspend), `/admin/users/{uid}/reset-quota`, and `/admin/users/{uid}/set-usage` is written to the new `sub_admin_activity` table with username + target email snapshots (survives sub-admin/user deletion). Super admin reads it via `GET /admin/sub-admins/activity` and sees it in the Sub Admins page UI (pagination + search + per-sub-admin filter).
- **Dashboard gating** — "Free Tier Quota" and "Last 7 Days — Usage Overview" sections are now hidden for sub-admins (defense-in-depth: App.jsx already gated the Dashboard tab itself with `!isSub`, but the sections are also wrapped in `{!isSub && ...}` as a belt-and-braces measure).
- **App.jsx tab fix** — sub-admin now defaults to and is forced onto the Users tab (was landing on Dashboard which has no tab button to reach but still mounted the component).

**Three critical deploy fixes (the deploy FAILED twice without these):**
1. `rm -rf python_modules` — this directory had grown to 8.9M with a 4 MB `pydantic_core/_pydantic_core.cpython-313-wasm32-emscripten.so` duplicate. Bundling it pushed the worker over the 3 MiB free-plan limit (error 10027). It's not imported by any code (`entry.py` uses the `app` package from the project root) — it's purely forbidden cruft.
2. `rm -rf .venv-workers/lib` — the redundant macOS duplicate of `.venv-workers/pyodide-venv/lib` that doubles bundle size. Already documented but had crept back.
3. `pydantic-core<2.27` pin in `pyproject.toml` — `pydantic_core 2.27.2` makes an extra `os.urandom()` call at import time that Cloudflare's `_cloudflare/entropy_import_context.py` doesn't cover → `RuntimeError: 1 unexpected leftover getentropy calls` (10021) on every cold start. Pinning below 2.27 avoids the extra call. Without this pin, the deploy bundles successfully but fails validation when the worker tries to initialize.

**Auth system change (between Aug 8 and Aug 12):** The login endpoint now returns a JWT instead of the HMAC-signed `base64(json).sig` token. New response shape:
```json
{"ok":true,"access_token":"eyJ...","access_token_ttl_s":900,"role":"admin"}
```
Use `access_token` (not `token`) in API clients. TTL is 15 minutes (`access_token_ttl_s: 900`).

## QUOTA DO GOTCHA (Aug 8 — root cause of "always 10/10")
`env.QUOTA.get(uid)` with a RAW STRING throws `TypeError` on the DO namespace —
every quota RPC silently failed, `_usage_for` fell back to D1 (count 0) → popup
showed 10/10 forever. ALWAYS use `env.QUOTA.get(env.QUOTA.idFromName(uid))`.
Call sites: quotas.py get_quota, main.py _consume_quota, admin consume endpoint.
Inside QuotaDO, recover the name via `state.id.name()` (see `_self_uid`).
Admin test endpoint: POST /admin/users/{uid}/quota/consume (admin token) →
returns inc verdict; remaining must drop by 1 per call.
