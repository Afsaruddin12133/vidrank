# DEPLOY NOTE — READ BEFORE EVERY BACKEND DEPLOY (learned the hard way)

## The ONLY way to deploy this worker
```bash
cd /Users/macm1/Desktop/vidrank/backend
mv .venv_bak /tmp/venv_bak_backup   # if present — macOS venv MUST NOT be in the dir
rm -rf .venv-workers/lib            # if present — redundant macOS duplicate, DOUBLES bundle size
pywrangler deploy
```

`pywrangler` (from `uv tool install workers-py`) is REQUIRED. It builds WASM/Pyodide-compatible
wheels into `.venv-workers/pyodide-venv`. Plain `wrangler deploy` or `npx wrangler deploy` WILL
FAIL with `ModuleNotFoundError: No module named 'fastapi'` (10021) — wrangler does NOT resolve
pyproject.toml deps itself.

## Never do these again
1. **NEVER manually copy packages from `.venv_bak`/`.venv` into `python_modules`.** They are
   macOS (CPython) builds — they CANNOT run on Cloudflare's WASM runtime. Result: confusing
   import errors (`annotated_doc`, `pydantic_core`, `fastapi`, …) one at a time.
2. **NEVER create a `requirements.txt`** — dependency resolution is pyproject.toml-based,
   done by pywrangler (uv).
3. **NEVER leave `.venv`, `.venv_bak`, or a duplicate `.venv-workers/lib` in the deploy dir.**
   Wrangler bundles what's in the folder → 10027 "exceeded the size limit of 3 MiB".
   The successful bundle was ~4.4MB duplicate-free = under the 3MiB (gzip) free limit.
4. There are NO WASM wheels on PyPI (`pip`/`uv` won't find pydantic_core for wasm32) — do not
   try `pip download --platform emscripten...`; pywrangler's configured resolver handles it.

## Verification after deploy (all must be 200)
```bash
curl -s https://vidrank-backend.fahad288ali.workers.dev/healthz          # {"ok":true}
# login → token, then:
curl -s https://vidrank-backend.fahad288ali.workers.dev/admin/free-quota -H "Authorization: Bearer $TOKEN"  # 200 (was 404)
curl -s https://vidrank-backend.fahad288ali.workers.dev/admin/users -H "Authorization: Bearer $TOKEN"        # users have photo_url
```

## Other facts
- Account: Fahad288ali@gmail.com / Account ID 888ad088a0b226524650478393ad1561
- Live worker: https://vidrank-backend.fahad288ali.workers.dev (Version ID efe2fe5b-f400-47b5-84f7-abb9d956820b, Aug 8 deploy)
- Admin password: `#admin23CHECK` → POST /admin/login → Bearer token (expires 8h)
- Free plan worker size limit: 3 MiB gzip.## QUOTA DO GOTCHA (Aug 8 — root cause of "always 10/10")
`env.QUOTA.get(uid)` with a RAW STRING throws `TypeError` on the DO namespace —
every quota RPC silently failed, `_usage_for` fell back to D1 (count 0) → popup
showed 10/10 forever. ALWAYS use `env.QUOTA.get(env.QUOTA.idFromName(uid))`.
Call sites: quotas.py get_quota, main.py _consume_quota, admin consume endpoint.
Inside QuotaDO, recover the name via `state.id.name()` (see `_self_uid`).
Admin test endpoint: POST /admin/users/{uid}/quota/consume (admin token) →
returns inc verdict; remaining must drop by 1 per call.
