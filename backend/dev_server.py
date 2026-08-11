"""Local dev server: run the same FastAPI app natively with uvicorn - no pyodide,
no rebundle, instant reload. Deploy still goes through pywrangler unchanged.

Usage:  uv run python dev_server.py       (from backend/)
Uses the same local D1 sqlite file pywrangler dev uses (.wrangler/state/v3/d1/...);
if it doesn't exist yet, bootstraps ./devlocal.db from migrations/001_init.sql.
DO bindings (QUOTA/RATESTATE) and KV/AI/queues are no-ops here: /admin/* and
DB-backed routes work; /v1/chat paths that hit Durable Objects fail loudly.
"""
from __future__ import annotations

import glob
import json
import sqlite3
import time
from pathlib import Path

from app import db
from app.main import app


class _Stmt:
    def __init__(self, db: "SQLiteD1", sql: str):
        self._db, self._sql, self._params = db, sql, None

    def bind(self, *params) -> "_Stmt":
        self._params = params
        return self

    def _exec(self):
        with self._db._conn() as c:
            return c.execute(self._sql, self._params or ())

    async def run(self):
        self._exec()
        return type("R", (), {"success": True})()

    async def first(self):
        r = self._exec().fetchone()
        return dict(r) if r else None

    async def all(self):
        cursor = self._exec()
        rows = [dict(r) for r in cursor.fetchall()]
        # Get column names from cursor description
        columns = [{"name": col[0]} for col in cursor.description] if cursor.description else []
        # Return object with results and columns attributes to match D1 API
        result = type("R", (), {
            "results": rows,
            "columns": columns
        })()
        return result


class SQLiteD1:
    """Minimal D1-compatible wrapper over sqlite3 (prepare/bind/run/first/all)."""

    def __init__(self, path: str):
        self._path = path

    def _conn(self):
        c = sqlite3.connect(self._path)
        c.row_factory = sqlite3.Row
        return c

    def prepare(self, sql: str):
        return _Stmt(self, sql)

    def exec(self, sql: str):
        with self._conn() as c:
            c.executescript(sql)


class _DO:
    def __getattr__(self, name):
        async def _noop(*a, **k):
            return None
        return _noop


class _KV:
    """In-memory KV shim so cache layer (exact/semantic) works locally; lost on restart."""

    def __init__(self):
        self._d = {}

    async def get(self, k, _type=None):
        return self._d.get(k)

    async def put(self, k, v, expiration_ttl=None):
        self._d[k] = v


class _DOStub:
    """env.QUOTA.get(uid) / env.RATESTATE.get(id) -> async no-op (admin routes never touch these)."""

    def get(self, _id):
        return _DO()


class _KVFile:
    """Persistent file-backed KV so exact/semantic caches actually work in local dev.

    Files live under .wrangler/state/v3/kv/dev-kv/ (one file per key, JSON value).
    get/put mirror the Workers KV API shape (get(key, type), put(key, value, ttl)).
    """

    def __init__(self, root: str | None = None):
        self._root = Path(root or ".wrangler/state/v3/kv/dev-kv")
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.replace("/", "_").replace(":", "_")
        return self._root / f"{safe}.json"

    async def get(self, key: str, _type: str = "text"):
        p = self._path(key)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
            if data.get("exp") and time.time() > data["exp"]:
                p.unlink(missing_ok=True)
                return None
            return data.get("value")
        except Exception:
            return None

    async def put(self, key: str, value: str, expiration_ttl: int | None = None) -> bool:
        exp = int(time.time()) + expiration_ttl if expiration_ttl else None
        try:
            self._path(key).write_text(json.dumps({"value": value, "exp": exp}))
            return True
        except Exception:
            return False

    async def list(self, prefix: str = "") -> list[str]:
        out = []
        for p in self._root.glob("*.json"):
            key = p.stem
            if key.startswith(prefix):
                out.append(key)
        return out


def _d1_path() -> str:
    hits = sorted(glob.glob(".wrangler/state/v3/d1/miniflare-D1DatabaseObject/*.sqlite"))
    # Filter out metadata files
    hits = [f for f in hits if "metadata" not in f]
    if hits:
        return hits[-1]
    local = Path("devlocal.db")
    if not local.exists():
        print(f"Creating new local database: {local}")
        SQLiteD1(str(local)).exec(Path("migrations/001_init.sql").read_text())
    return str(local)


def _load_vars() -> dict:
    import os
    out = {}
    p = Path(".dev.vars")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            key = k.strip()
            val = v.strip().strip('"').strip("'")
            out[key] = val
            # Also set in os.environ so contracts.py can read it
            os.environ[key] = val
    for k in ("ENCRYPTION_KEY", "JWT_SECRET", "ADMIN_PASS"):
        out.setdefault(k, "dev-secret" if k != "ADMIN_PASS" else "#admin23CHECK")
    return out


class _Env:
    pass


def _make_env():
    e = _Env()
    e.DB = SQLiteD1(_d1_path())
    e.KV = _KV()
    e.QUOTA = _DOStub()
    e.RATESTATE = _DOStub()
    e.KV = _KVFile()
    for k, v in _load_vars().items():
        setattr(e, k, v)
    return e


# Injected before serving; reload=True re-imports this module, so state stays fresh.
app.state.env = _make_env()
app.state.flusher = db.BatchedFlusher(app.state.env)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("dev_server:app", host="127.0.0.1", port=8787, reload=True)
