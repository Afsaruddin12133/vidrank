#!/usr/bin/env python3
"""Manual Firebase sync script for local development."""
import asyncio
import os
import sys

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app import sync, db


class MockEnv:
    """Mock environment with Firestore URL and DB connection."""
    def __init__(self, db_path: str, firestore_url: str):
        self.FIRESTORE_DB_URL = firestore_url
        # Create a mock DB binding
        import sqlite3
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        
    def prepare(self, sql: str):
        """Mock D1 prepare() interface."""
        return MockStmt(self._conn, sql)


class MockStmt:
    """Mock D1 statement."""
    def __init__(self, conn, sql: str):
        self._conn = conn
        self._sql = sql
        self._params = []
        
    def bind(self, *params):
        self._params = params
        return self
        
    async def run(self):
        cursor = self._conn.execute(self._sql, self._params)
        self._conn.commit()
        return type("R", (), {"success": True, "meta": {"changes": cursor.rowcount}})()
        
    async def all(self):
        cursor = self._conn.execute(self._sql, self._params)
        rows = [dict(r) for r in cursor.fetchall()]
        return type("R", (), {"results": rows})()


async def main():
    # Load .dev.vars
    vars_file = os.path.join(os.path.dirname(__file__), '.dev.vars')
    firestore_url = None
    
    if os.path.exists(vars_file):
        with open(vars_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith('FIRESTORE_DB_URL'):
                    firestore_url = line.split('=', 1)[1].strip().strip('"')
                    
    if not firestore_url:
        print("❌ FIRESTORE_DB_URL not found in .dev.vars")
        return
        
    # Find D1 database
    db_dir = ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
    db_files = [f for f in os.listdir(db_dir) if f.endswith('.sqlite') and f != 'metadata.sqlite']
    
    if not db_files:
        print("❌ No D1 database found")
        return
        
    db_path = os.path.join(db_dir, db_files[0])
    print(f"📊 Database: {db_path}")
    print(f"🔥 Firestore: {firestore_url}")
    print()
    
    # Create mock env
    env = MockEnv(db_path, firestore_url)
    env.DB = env
    
    # Sync plans
    print("⏳ Syncing plans from Firebase...")
    try:
        await sync.sync_plans(env)
        print("✅ Plans synced")
    except Exception as e:
        print(f"⚠️  Plans sync failed: {e}")
    
    # Sync users
    print("⏳ Syncing users from Firebase...")
    try:
        await sync.sync_users(env)
        print("✅ Users synced")
    except Exception as e:
        print(f"❌ Users sync failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Count users
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    
    cursor = conn.execute("SELECT tier, COUNT(*) FROM users GROUP BY tier")
    breakdown = dict(cursor.fetchall())
    
    print()
    print(f"📊 Total users in D1: {total}")
    print(f"   - Free: {breakdown.get('free', 0)}")
    print(f"   - Pro: {breakdown.get('pro', 0)}")
    print()
    print("✅ Sync complete! Refresh your dashboard.")


if __name__ == "__main__":
    asyncio.run(main())
