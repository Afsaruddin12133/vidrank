import os
#!/usr/bin/env python3
import json
import urllib.request
import urllib.error

API_KEY = os.environ.get("PADDLE_API_KEY", "")
BASE_URL = "https://sandbox-api.paddle.com"
CUSTOMER_ID = "ctm_01m0tqqd551vpm7j8bc49jy02w"

# Test minting portal session
url = f"{BASE_URL}/customers/{CUSTOMER_ID}/portal-sessions"
req = urllib.request.Request(
    url,
    data=b"{}",
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        print("SUCCESS! Portal Session:", data)
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}:", e.read().decode("utf-8"))
except Exception as e:
    print("Error:", e)
