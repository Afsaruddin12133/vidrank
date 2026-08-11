import urllib.request
import json

def check_admin_user():
    # Login as admin to get token
    login_url = "https://vidrank-backend.fahad288ali.workers.dev/admin/login"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Content-Type": "application/json"
    }
    payload = json.dumps({"password": "#admin23CHECK"}).encode("utf-8")
    
    req = urllib.request.Request(login_url, data=payload, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
        token = data.get("token")
        print("1. Admin Login Success. Token:", token[:20] + "...")

    # Fetch user winudemy@gmail.com from paginated API
    users_url = "https://vidrank-backend.fahad288ali.workers.dev/admin/users/paged?q=winudemy@gmail.com"
    req_users = urllib.request.Request(users_url, headers={
        "User-Agent": "Mozilla/5.0",
        "Authorization": f"Bearer {token}"
    })
    with urllib.request.urlopen(req_users) as resp:
        res = json.loads(resp.read().decode())
        print("2. Live DB User Record for winudemy@gmail.com:")
        print(json.dumps(res, indent=2))

if __name__ == "__main__":
    check_admin_user()
