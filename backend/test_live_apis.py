import urllib.request
import urllib.error
import json

BASE_URL = "https://vidrank-backend.fahad288ali.workers.dev"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def test_api():
    print("--- 1. Testing /healthz ---")
    req = urllib.request.Request(f"{BASE_URL}/healthz", headers={"User-Agent": UA})
    with urllib.request.urlopen(req) as resp:
        print(f"Status: {resp.status}, Body: {resp.read().decode()}")

    print("\n--- 2. Testing /admin/login ---")
    data = json.dumps({"password": "#admin23CHECK"}).encode()
    req = urllib.request.Request(f"{BASE_URL}/admin/login", data=data, headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
        print(f"Status: {resp.status}, Token issued: {res.get('token')[:20]}...")
        admin_token = res.get("token")

    headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json", "User-Agent": UA}

    print("\n--- 3. Testing GET /admin/users/paged ---")
    req = urllib.request.Request(f"{BASE_URL}/admin/users/paged", headers=headers)
    with urllib.request.urlopen(req) as resp:
        users_data = json.loads(resp.read().decode())
        print(f"Status: {resp.status}, Total Users: {users_data.get('total')}")
        test_uid = users_data.get("users", [{}])[0].get("firebase_uid") or "test_uid"
        print(f"Sample User UID: {test_uid}")

    print(f"\n--- 4. Testing PATCH /admin/users/{test_uid} (Set Pro + Active) ---")
    data = json.dumps({"tier": "pro", "is_active": 1}).encode()
    req = urllib.request.Request(f"{BASE_URL}/admin/users/{test_uid}", data=data, headers=headers, method="PATCH")
    with urllib.request.urlopen(req) as resp:
        print(f"Status: {resp.status}, Body: {resp.read().decode()}")

    print(f"\n--- 5. Testing POST /admin/users/{test_uid}/reset-quota ---")
    req = urllib.request.Request(f"{BASE_URL}/admin/users/{test_uid}/reset-quota", data=b"{}", headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        print(f"Status: {resp.status}, Body: {resp.read().decode()}")

    print(f"\n--- 6. Testing POST /admin/users/{test_uid}/set-usage ---")
    data = json.dumps({"usage_count": 3}).encode()
    req = urllib.request.Request(f"{BASE_URL}/admin/users/{test_uid}/set-usage", data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Status: {resp.status}, Body: {resp.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"HTTPError Status: {e.code}, Body: {e.read().decode()}")

if __name__ == "__main__":
    test_api()
