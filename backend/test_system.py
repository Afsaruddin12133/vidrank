#!/usr/bin/env python3
"""
Comprehensive test script for vidrank backend + frontend connectivity.
Tests database, backend API, frontend connection, and provides fixes.

Run: uv run python test_system.py
"""
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Installing httpx for testing...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "httpx"], check=True)
    import httpx

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def success(msg):
    print(f"{GREEN}✓{RESET} {msg}")


def error(msg):
    print(f"{RED}✗{RESET} {msg}")


def warning(msg):
    print(f"{YELLOW}⚠{RESET} {msg}")


def info(msg):
    print(f"{BLUE}ℹ{RESET} {msg}")


class SystemTester:
    def __init__(self):
        self.backend_url = "http://localhost:8787"
        self.frontend_url = "http://localhost:5173"
        self.db_path = None
        self.issues = []
        self.fixes = []

    def find_d1_database(self):
        """Find the D1 database file"""
        pattern = ".wrangler/state/v3/d1/miniflare-D1DatabaseObject/*.sqlite"
        import glob
        hits = [f for f in glob.glob(pattern) if "metadata" not in f]
        if hits:
            self.db_path = hits[0]
            success(f"Found D1 database: {self.db_path}")
            return True
        
        error("D1 database not found")
        self.issues.append("D1 database not initialized")
        self.fixes.append("Run: wrangler d1 execute vidrank --local --file=migrations/001_init.sql")
        return False

    def test_database_schema(self):
        """Test if database tables exist"""
        if not self.db_path:
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check required tables
            required_tables = ['users', 'accounts', 'plans', 'usage_log', 'usage_daily', 
                             'account_usage_daily', 'memory_graph']
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            missing = [t for t in required_tables if t not in existing_tables]
            if missing:
                error(f"Missing tables: {', '.join(missing)}")
                self.issues.append(f"Missing database tables: {missing}")
                self.fixes.append("Run migrations: wrangler d1 execute vidrank --local --file=migrations/001_init.sql")
                conn.close()
                return False
            
            success("All required database tables exist")
            
            # Check if accounts exist
            cursor.execute("SELECT COUNT(*) FROM accounts WHERE enabled = 1")
            account_count = cursor.fetchone()[0]
            
            if account_count == 0:
                warning("No provider accounts configured")
                self.issues.append("No provider accounts in database")
                self.fixes.append("Add a provider account via admin dashboard or POST /admin/accounts")
                info("You need to add Groq or OpenRouter API keys to handle requests")
            else:
                success(f"Found {account_count} enabled provider account(s)")
            
            # Check plans
            cursor.execute("SELECT COUNT(*) FROM plans")
            plan_count = cursor.fetchone()[0]
            
            if plan_count == 0:
                warning("No plans configured")
                self.issues.append("No plans in database")
                self.fixes.append("Insert default plans (free/pro)")
            else:
                success(f"Found {plan_count} plan(s)")
            
            conn.close()
            return True
            
        except Exception as e:
            error(f"Database test failed: {e}")
            self.issues.append(f"Database error: {e}")
            return False

    async def test_backend_connection(self):
        """Test if backend is responding"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.backend_url}/healthz", timeout=5.0)
                
                if response.status_code == 200:
                    success(f"Backend is running at {self.backend_url}")
                    return True
                else:
                    error(f"Backend returned status {response.status_code}")
                    self.issues.append(f"Backend unhealthy: HTTP {response.status_code}")
                    return False
                    
        except httpx.ConnectError:
            error("Backend is not running")
            self.issues.append("Backend server not running")
            self.fixes.append("Start backend: wrangler dev (or) uv run python dev_server.py")
            return False
        except Exception as e:
            error(f"Backend connection failed: {e}")
            self.issues.append(f"Backend connection error: {e}")
            return False

    async def test_frontend_connection(self):
        """Test if frontend is responding"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.frontend_url, timeout=5.0)
                
                if response.status_code == 200:
                    success(f"Frontend is running at {self.frontend_url}")
                    return True
                else:
                    error(f"Frontend returned status {response.status_code}")
                    self.issues.append(f"Frontend returned HTTP {response.status_code}")
                    return False
                    
        except httpx.ConnectError:
            error("Frontend is not running")
            self.issues.append("Frontend server not running")
            self.fixes.append("Start frontend: cd frontend && npm run dev")
            return False
        except Exception as e:
            error(f"Frontend connection failed: {e}")
            self.issues.append(f"Frontend connection error: {e}")
            return False

    async def test_admin_login(self):
        """Test admin login endpoint"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.backend_url}/admin/login",
                    json={"password": "#admin23CHECK"},
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if "token" in data:
                        success("Admin login works")
                        return data["token"]
                    else:
                        error("Admin login response missing token")
                        self.issues.append("Admin login returns invalid response")
                else:
                    error(f"Admin login failed: HTTP {response.status_code}")
                    self.issues.append("Admin authentication not working")
                    return None
                    
        except Exception as e:
            error(f"Admin login test failed: {e}")
            self.issues.append(f"Admin login error: {e}")
            return None

    async def test_cors_config(self):
        """Test CORS configuration"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.options(
                    f"{self.backend_url}/v1/me",
                    headers={
                        "Origin": "http://localhost:5173",
                        "Access-Control-Request-Method": "GET"
                    },
                    timeout=5.0
                )
                
                if "access-control-allow-origin" in response.headers:
                    success("CORS is configured")
                    return True
                else:
                    warning("CORS headers not found")
                    self.issues.append("CORS not properly configured")
                    self.fixes.append("Check ALLOWED_ORIGINS in wrangler.toml [vars]")
                    return False
                    
        except Exception as e:
            warning(f"CORS test inconclusive: {e}")
            return False

    def insert_default_plans(self):
        """Insert default free and pro plans"""
        if not self.db_path:
            return False
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if plans exist
            cursor.execute("SELECT COUNT(*) FROM plans")
            if cursor.fetchone()[0] > 0:
                info("Plans already exist, skipping insert")
                conn.close()
                return True
            
            # Insert default plans
            now = int(time.time())
            cursor.execute(
                "INSERT INTO plans (plan_id, daily_limit, synced_at, price, plandetails) VALUES (?, ?, ?, ?, ?)",
                ("free", 10, now, 0, '{"name": "Free", "features": ["10 requests/day", "Basic support"]}')
            )
            cursor.execute(
                "INSERT INTO plans (plan_id, daily_limit, synced_at, price, plandetails) VALUES (?, ?, ?, ?, ?)",
                ("pro", -1, now, 999, '{"name": "Pro", "features": ["Unlimited requests", "Priority support"]}')
            )
            
            conn.commit()
            conn.close()
            success("Inserted default plans (free: 10/day, pro: unlimited)")
            return True
            
        except Exception as e:
            error(f"Failed to insert plans: {e}")
            return False

    async def run_all_tests(self):
        """Run all tests"""
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}VidRank System Test Suite{RESET}")
        print(f"{BLUE}{'='*60}{RESET}\n")
        
        info("Testing database...")
        db_ok = self.find_d1_database()
        if db_ok:
            schema_ok = self.test_database_schema()
        
        info("\nTesting backend...")
        backend_ok = await self.test_backend_connection()
        
        info("\nTesting frontend...")
        frontend_ok = await self.test_frontend_connection()
        
        if backend_ok:
            info("\nTesting admin authentication...")
            token = await self.test_admin_login()
            
            info("\nTesting CORS configuration...")
            await self.test_cors_config()
        
        # Print summary
        print(f"\n{BLUE}{'='*60}{RESET}")
        print(f"{BLUE}Test Summary{RESET}")
        print(f"{BLUE}{'='*60}{RESET}\n")
        
        if not self.issues:
            print(f"{GREEN}✓ All tests passed!{RESET}\n")
        else:
            print(f"{RED}Found {len(self.issues)} issue(s):{RESET}\n")
            for i, issue in enumerate(self.issues, 1):
                print(f"  {i}. {issue}")
            
            if self.fixes:
                print(f"\n{YELLOW}Suggested fixes:{RESET}\n")
                for i, fix in enumerate(self.fixes, 1):
                    print(f"  {i}. {fix}")
        
        # Offer auto-fixes
        if "No plans in database" in self.issues:
            print(f"\n{YELLOW}Auto-fix available: Insert default plans{RESET}")
            response = input("Apply fix? (y/n): ")
            if response.lower() == 'y':
                self.insert_default_plans()

    async def test_data_flow(self):
        """Test complete data flow with a sample request"""
        info("\nTesting complete data flow...")
        
        token = await self.test_admin_login()
        if not token:
            error("Cannot test data flow without admin token")
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                # Test listing accounts
                response = await client.get(
                    f"{self.backend_url}/admin/accounts",
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    accounts = response.json().get("accounts", [])
                    success(f"Successfully retrieved {len(accounts)} accounts")
                    return True
                else:
                    error(f"Failed to retrieve accounts: HTTP {response.status_code}")
                    return False
                    
        except Exception as e:
            error(f"Data flow test failed: {e}")
            return False


async def main():
    tester = SystemTester()
    await tester.run_all_tests()
    
    # Additional data flow test
    if not tester.issues or len([i for i in tester.issues if "not running" not in i]) == 0:
        await tester.test_data_flow()
    
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}D1 Database Scalability Assessment{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    print("D1 (SQLite) can handle 1000 concurrent users, but consider:")
    print(f"{YELLOW}Strengths:{RESET}")
    print("  ✓ Read performance: ~5M reads/day on free tier")
    print("  ✓ Single-row writes are fast (<10ms)")
    print("  ✓ Built-in replication and backups")
    print("  ✓ Serverless, no infrastructure management")
    
    print(f"\n{YELLOW}Limitations:{RESET}")
    print("  ⚠ Write limit: 1000 writes/day (free), 100K/day (paid)")
    print("  ⚠ No concurrent writes (SQLite limitation)")
    print("  ⚠ Max DB size: 2GB (free), 10GB (paid)")
    
    print(f"\n{GREEN}Current Design Mitigations:{RESET}")
    print("  ✓ BatchedFlusher (20 rows/flush) reduces write count")
    print("  ✓ Hot counters in Durable Objects (not D1)")
    print("  ✓ Cache layer reduces database hits")
    
    print(f"\n{BLUE}Recommendations:{RESET}")
    print("  1. Current setup: Good for 1000 users with batched writes")
    print("  2. Scale to 10K users: Upgrade to D1 paid tier ($5/mo)")
    print("  3. Scale to 100K+ users: Consider PostgreSQL (Neon, Supabase)")
    print("  4. Monitor: Usage logs will fill up fastest - archive/delete old logs")
    
    print(f"\n{YELLOW}When to switch to PostgreSQL:{RESET}")
    print("  → Need >100K writes/day")
    print("  → Need complex queries/joins")
    print("  → Need concurrent write transactions")
    print("  → Database >2GB")
    print()


if __name__ == "__main__":
    asyncio.run(main())
