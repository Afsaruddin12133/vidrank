"""Local dev server: run the same FastAPI app natively with uvicorn — no pyodide,
no rebundle, instant reload. Deploy still goes through pywrangler unchanged.

Usage:  uv run python devlocal.py        (from backend/)
Uses the same local D1 sqlite file pywrangler dev uses (.wrangler/state/v3/d1/...);
if it doesn't exist yet, bootstraps ./devlocal.db from migrations/001_init.sql.
DO bindings (QUOTA/RATESTATE) and KV/AI/queues are no-ops here: /admin/* and
DB-backed routes work; /v1/chat paths that hit Durable Objects fail loudly.
"""
from __future__ import annotations

import glob
import sqlite3
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
        return type("R", (), {"success": True})

    async def first(self):
        r = self._exec().fetchone()
        return dict(r) if r else None

    async def all(self):
        return [dict(r) for r in self._exec().fetchall()]


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


class _DOStub:
    """env.QUOTA.get(uid) / env.RATESTATE.get(id) -> async no-op (admin routes never touch these)."""

    def get(self, _id):
        return _DO()


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
    out = {}
    p = Path(".dev.vars")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip().strip('"').strip("'")
    for k in ("ENCRYPTION_KEY", "JWT_SECRET"):
        out.setdefault(k, "dev-secret")
    return out


class _Env:
    pass


app.state.env = _make_env() if False else None  # placeholder, replaced below
