import os
#!/usr/bin/env python3
import json
import urllib.request
import urllib.error

API_KEY = os.environ.get("PADDLE_API_KEY", "")
BASE_URL = "https://api.paddle.com"

def paddle_req(endpoint, method="GET", body=None):
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        try:
            return json.loads(err)
        except:
            return {"success": False, "error": err}
    except Exception as e:
        return {"success": False, "error": str(e)}

print("🔍 1. Fetching Live Products...")
products_res = paddle_req("products")
products = products_res.get("data", [])
print(f"Found {len(products)} live products:")
for p in products:
    print(f" • Product: {p.get('name')} (ID: {p.get('id')}, Status: {p.get('status')})")

print("\n🔍 2. Fetching Live Prices...")
prices_res = paddle_req("prices")
prices = prices_res.get("data", [])
print(f"Found {len(prices)} live prices:")
for pr in prices:
    unit_price = pr.get("unit_price", {})
    billing_cycle = pr.get("billing_cycle", {})
    amount = float(unit_price.get("amount", 0)) / 100
    currency = unit_price.get("currency_code", "USD")
    interval = f"{billing_cycle.get('frequency')} {billing_cycle.get('interval')}" if billing_cycle else "one-off"
    print(f" • Price ID: {pr.get('id')} | Product ID: {pr.get('product_id')} | {amount} {currency} / {interval} | Status: {pr.get('status')}")

print("\n🔍 3. Fetching Notification Destinations (Webhooks)...")
dest_res = paddle_req("notification-destinations")
destinations = dest_res.get("data", [])
print(f"Found {len(destinations)} notification destinations:")
for d in destinations:
    print(f" • Destination ID: {d.get('id')} | URL: {d.get('endpoint_url')} | Status: {d.get('status')} | Subscribed Events: {len(d.get('events', []))}")
