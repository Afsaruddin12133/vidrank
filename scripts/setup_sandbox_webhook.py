import os
#!/usr/bin/env python3
import json
import urllib.request
import urllib.error

SANDBOX_API_KEY = os.environ.get("PADDLE_API_KEY", "")
BASE_URL = "https://sandbox-api.paddle.com"

def paddle_req(endpoint, method="GET", body=None):
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {SANDBOX_API_KEY}",
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

print("🔍 1. Checking existing Sandbox Notification Destinations...")
res = paddle_req("notification-settings")
destinations = res.get("data", [])
print(f"Found {len(destinations)} destination(s):")
for d in destinations:
    print(f" • ID: {d.get('id')} | URL: {d.get('destination')} | Active: {d.get('active')}")
    print(f"   Endpoint Secret: {d.get('endpoint_secret_key')}")

webhook_url = "https://vidrank-backend.fahad288ali.workers.dev/v1/billing/paddle-webhook"

all_events = [
    "subscription.created",
    "subscription.activated",
    "subscription.updated",
    "subscription.canceled",
    "subscription.past_due",
    "subscription.paused",
    "subscription.resumed",
    "subscription.imported",
    "customer.created",
    "customer.updated",
    "transaction.completed",
    "transaction.paid",
    "transaction.billed",
    "transaction.canceled",
    "transaction.created",
    "transaction.ready"
]

if not destinations:
    print("\n🚀 Creating Sandbox Notification Destination...")
    body = {
        "description": "VidRank Sandbox Backend Webhook",
        "destination": webhook_url,
        "type": "url",
        "subscribed_events": all_events
    }
    create_res = paddle_req("notification-settings", method="POST", body=body)
    data = create_res.get("data", {})
    print("Created Destination ID:", data.get("id"))
    print("Signing Secret Key:", data.get("endpoint_secret_key"))
else:
    dest_id = destinations[0].get("id")
    print(f"\n🔄 Updating Destination {dest_id} with all 16 events...")
    update_res = paddle_req(f"notification-settings/{dest_id}", method="PATCH", body={
        "subscribed_events": all_events,
        "destination": webhook_url,
        "active": True
    })
    print("Updated Events Count:", len(update_res.get("data", {}).get("subscribed_events", [])))
