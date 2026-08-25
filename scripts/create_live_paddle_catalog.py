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

print("🚀 1. Creating Product 'VidRank Pro' in Live Paddle...")
prod_body = {
    "name": "VidRank Pro",
    "description": "AI-Powered YouTube SEO, Tag & Description Optimizer for Creators",
    "tax_category": "standard"
}
prod_res = paddle_req("products", method="POST", body=prod_body)
product_data = prod_res.get("data", {})
product_id = product_data.get("id")
print(f"   ✓ Product Created: {product_data.get('name')} (ID: {product_id})")

if not product_id:
    print("❌ Failed to create product:", prod_res)
    exit(1)

print("\n🚀 2. Creating Prices for VidRank Pro...")

# Monthly price: $3.99 USD / month
price_monthly_body = {
    "product_id": product_id,
    "description": "VidRank Pro Monthly ($3.99/mo)",
    "unit_price": {
        "amount": "399",
        "currency_code": "USD"
    },
    "billing_cycle": {
        "interval": "month",
        "frequency": 1
    }
}
price_monthly_res = paddle_req("prices", method="POST", body=price_monthly_body)
price_monthly_data = price_monthly_res.get("data", {})
price_monthly_id = price_monthly_data.get("id")
print(f"   ✓ Monthly Price Created: {price_monthly_id} ($3.99 USD / month)")

# Yearly price: $38.30 USD / year (~$3.19/mo, 20% discount)
price_yearly_body = {
    "product_id": product_id,
    "description": "VidRank Pro Yearly ($38.30/yr - Save 20%)",
    "unit_price": {
        "amount": "3830",
        "currency_code": "USD"
    },
    "billing_cycle": {
        "interval": "year",
        "frequency": 1
    }
}
price_yearly_res = paddle_req("prices", method="POST", body=price_yearly_body)
price_yearly_data = price_yearly_res.get("data", {})
price_yearly_id = price_yearly_data.get("id")
print(f"   ✓ Yearly Price Created: {price_yearly_id} ($38.30 USD / year)")

print("\n🚀 3. Creating Live Notification Destination (Webhook)...")
webhook_url = "https://vidrank-backend.fahad288ali.workers.dev/v1/billing/paddle-webhook"
dest_body = {
    "endpoint_url": webhook_url,
    "description": "VidRank Production Cloudflare Worker Webhook",
    "events": [
        "subscription.created",
        "subscription.activated",
        "subscription.updated",
        "subscription.canceled",
        "subscription.past_due",
        "subscription.paused",
        "subscription.resumed",
        "transaction.completed",
        "transaction.paid"
    ]
}
dest_res = paddle_req("notification-destinations", method="POST", body=dest_body)
dest_data = dest_res.get("data", {})
dest_id = dest_data.get("id")
endpoint_secret_key = dest_data.get("endpoint_secret_key")
print(f"   ✓ Webhook Destination Created: {dest_id}")
print(f"   ✓ Signing Secret Key: {endpoint_secret_key}")

# Summary output
print("\n" + "=" * 60)
print("PADDLE LIVE SETUP COMPLETED SUCCESSFULLY!")
print("=" * 60)
print(f"Product ID: {product_id}")
print(f"Monthly Price ID: {price_monthly_id}")
print(f"Yearly Price ID: {price_yearly_id}")
print(f"Notification Destination ID: {dest_id}")
print(f"Webhook Secret Key: {endpoint_secret_key}")
print("=" * 60)
