import os
#!/usr/bin/env python3
"""Fix and create 100% test discount + add vidrank.ai domain."""
import json
import urllib.request
import urllib.error

API_KEY = os.environ.get("PADDLE_API_KEY", "")
BASE_URL = "https://api.paddle.com"

def paddle_req(endpoint, method="GET", body=None):
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

# Fix 1: Add vidrank.ai domain with correct field name
print("Adding vidrank.ai checkout domain...")
add_res = paddle_req("checkout-domains", method="POST", body={"domain": "vidrank.ai"})
print(json.dumps(add_res, indent=2))

# Fix 2: Discount code must match ^[a-zA-Z0-9]{1,32}$ — no dashes
print("\nCreating 100% test discount (alphanumeric code only)...")
discount_body = {
    "type": "percentage",
    "amount": "100",
    "description": "End-to-end live integration test INTERNAL",
    "enabled_for_checkout": True,
    "code": "VIDRANKTEST100",   # alphanumeric only
    "recur": False,
    "usage_limit": 1
}
disc_res = paddle_req("discounts", method="POST", body=discount_body)
disc_data = disc_res.get("data", {})
if disc_data.get("id"):
    print(f"\n✓ Discount created successfully!")
    print(f"  Code: {disc_data.get('code')}")
    print(f"  ID: {disc_data.get('id')}")
    print(f"  Amount: {disc_data.get('amount')}%")
    print(f"  Usage limit: {disc_data.get('usage_limit')}")
    print(f"  Status: {disc_data.get('status')}")
else:
    print("Error:", json.dumps(disc_res, indent=2))
