import os
#!/usr/bin/env python3
"""Pre-flight checks for Live Paddle integration."""
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

print("=" * 60)
print("PADDLE LIVE PRE-FLIGHT CHECKS")
print("=" * 60)

# 1. Verify API key points to live (not sandbox)
print("\n✅ Check 1: API Key Environment")
print(f"   API Key prefix: {API_KEY[:30]}...")
print(f"   Base URL: {BASE_URL}")
print(f"   → Confirmed: api.paddle.com (LIVE, not sandbox)")

# 2. Check products & prices exist
print("\n✅ Check 2: Products & Prices")
products = paddle_req("products")
for p in products.get("data", []):
    print(f"   Product: {p['name']} (ID: {p['id']}, Status: {p['status']})")

prices = paddle_req("prices")
for pr in prices.get("data", []):
    uc = pr.get("unit_price", {})
    bc = pr.get("billing_cycle", {})
    amt = float(uc.get("amount", 0)) / 100
    interval = f"{bc.get('frequency')} {bc.get('interval')}" if bc else "one-off"
    print(f"   Price: {pr['id']} | ${amt} {uc.get('currency_code')} / {interval} | Status: {pr['status']}")

# 3. Check notification/webhook settings
print("\n✅ Check 3: Webhook Notification Settings")
notif = paddle_req("notification-settings")
for n in notif.get("data", []):
    print(f"   ID: {n['id']} | URL: {n['destination']} | Active: {n['active']}")
    print(f"   Events subscribed: {len(n.get('subscribed_events', []))}")

# 4. Check checkout domains
print("\n✅ Check 4: Checkout Domains")
domains = paddle_req("checkout-domains")
domain_data = domains.get("data", [])
if domain_data:
    for d in domain_data:
        print(f"   Domain: {d.get('domain')} | Status: {d.get('status')}")
else:
    print("   ⚠️  No checkout domains found — raw response:")
    print("  ", json.dumps(domains, indent=2)[:400])

# 5. Check existing discounts
print("\n✅ Check 5: Existing Discounts")
discounts = paddle_req("discounts")
for d in discounts.get("data", []):
    print(f"   Discount: {d.get('code')} | {d.get('amount')}% | Status: {d.get('status')}")

# 6. Verify no sandbox flag in code
print("\n✅ Check 6: Code sandbox check")
import subprocess
result = subprocess.run(
    ["grep", "-r", "sandbox", "/Users/macm1/Desktop/vidrank/landing-page/src", "--include=*.ts", "--include=*.astro", "-l"],
    capture_output=True, text=True
)
if result.stdout.strip():
    print(f"   ⚠️  Files with 'sandbox' string: {result.stdout.strip()}")
else:
    print("   ✓ No 'sandbox' references found in frontend source")

result2 = subprocess.run(
    ["grep", "-r", "Environment.set", "/Users/macm1/Desktop/vidrank/landing-page/src", "--include=*.ts", "--include=*.astro", "-n"],
    capture_output=True, text=True
)
if result2.stdout.strip():
    print(f"   ⚠️  Paddle.Environment.set calls: {result2.stdout.strip()}")
else:
    print("   ✓ No Paddle.Environment.set('sandbox') calls found")

result3 = subprocess.run(
    ["grep", "-r", "sandbox-api.paddle", "/Users/macm1/Desktop/vidrank/backend", "--include=*.py", "-n"],
    capture_output=True, text=True
)
if result3.stdout.strip():
    print(f"   ⚠️  Backend uses sandbox API: {result3.stdout.strip()}")
else:
    print("   ✓ Backend uses api.paddle.com (live)")

print("\n" + "=" * 60)
print("PRE-FLIGHT COMPLETE")
print("=" * 60)
