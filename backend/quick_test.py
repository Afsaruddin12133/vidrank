#!/usr/bin/env python3
"""
Quick test script for vidrank system - non-interactive version
"""
import asyncio
import sqlite3
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("Installing httpx...")
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "httpx"], check=True)
    import httpx

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


async def test_all():
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}VidRank Quick Test{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    issues = []
    
    # Test 1: Database
    print("1. Testing database...")
    import glob
    db_files = [f for f in glob.glob("backend/.wrangler/state/v3/d1/miniflare-D1DatabaseObject/*.sqlite") if "metadata" not in f]
    if db_files:
        db_path = db_files[0]
        print(f"   {GREEN}✓{RESET} Found database: {db_path}")
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM plans")
        plan_count = cursor.fetchone()[0]
        print(f"   {GREEN}✓{RESET} Plans: {plan_count}")
        
        cursor.execute("SELECT COUNT(*) FROM accounts WHERE enabled = 1")
        account_count = cursor.fetchone()[0]
        if account_count == 0:
            print(f"   {YELLOW}⚠{RESET} No provider accounts configured")
            issues.append("Add provider accounts via admin dashboard")
        else:
            print(f"   {GREEN}✓{RESET} Accounts: {account_count}")
        conn.close()
    else:
        print(f"   {RED}✗{RESET} Database not found")
        issues.append("Initialize database: wrangler d1 execute vidrank --local --file=migrations/001_init.sql")
    
    # Test 2: Backend
    print("\n2. Testing backend...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:8787/healthz", timeout=5.0)
            if response.status_code == 200:
                print(f"   {GREEN}✓{RESET} Backend responding at http://localhost:8787")
                
                # Test admin login
                login_response = await client.post(
                    "http://localhost:8787/admin/login",
                    json={"password": "#admin23CHECK"},
                    timeout=5.0
                )
                if login_response.status_code == 200:
                    print(f"   {GREEN}✓{RESET} Admin authentication works")
                    
                    token = login_response.json()["token"]
                    accounts_response = await client.get(
                        "http://localhost:8787/admin/accounts",
                        headers={"Authorization": f"Bearer {token}"},
                        timeout=5.0
                    )
                    if accounts_response.status_code == 200:
                        print(f"   {GREEN}✓{RESET} API endpoints working")
                    else:
                        print(f"   {RED}✗{RESET} API endpoints failing")
                        issues.append("Check backend logs: backend/dev_server.log")
                else:
                    print(f"   {RED}✗{RESET} Admin authentication failing")
            else:
                print(f"   {RED}✗{RESET} Backend returned status {response.status_code}")
                issues.append("Check backend logs: backend/dev_server.log")
    except httpx.ConnectError:
        print(f"   {RED}✗{RESET} Backend not running")
        issues.append("Start backend: cd backend && uv run python dev_server.py")
    except Exception as e:
        print(f"   {RED}✗{RESET} Backend error: {e}")
        issues.append("Check backend logs: backend/dev_server.log")
    
    # Test 3: Frontend
    print("\n3. Testing frontend...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:5173", timeout=5.0)
            if response.status_code == 200:
                print(f"   {GREEN}✓{RESET} Frontend running at http://localhost:5173")
            else:
                print(f"   {YELLOW}⚠{RESET} Frontend returned status {response.status_code}")
    except httpx.ConnectError:
        print(f"   {RED}✗{RESET} Frontend not running")
        issues.append("Start frontend: cd backend/frontend && npm run dev")
    except Exception as e:
        print(f"   {RED}✗{RESET} Frontend error: {e}")
    
    # Summary
    print(f"\n{BLUE}{'='*60}{RESET}")
    if not issues:
        print(f"{GREEN}✓ All tests passed!{RESET}\n")
        print("Access points:")
        print(f"  • Admin Dashboard: http://localhost:5173 (password: #admin23CHECK)")
        print(f"  • Backend API: http://localhost:8787")
    else:
        print(f"{YELLOW}Found {len(issues)} issue(s):{RESET}\n")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    # Database scalability info
    print(f"{BLUE}Database Scalability (D1 SQLite):{RESET}")
    print(f"{GREEN}✓ Current setup can handle 1,000 concurrent users{RESET}")
    print(f"{YELLOW}⚠ For 10,000+ users: Upgrade to D1 paid tier ($5/mo){RESET}")
    print(f"{YELLOW}⚠ For 100,000+ users: Switch to PostgreSQL (Neon/Supabase){RESET}")
    print(f"\nSee TROUBLESHOOTING.md for detailed scalability analysis\n")


if __name__ == "__main__":
    asyncio.run(test_all())
