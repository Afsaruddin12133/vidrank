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

# Test notification-settings endpoint
webhook_url = "https://vidrank-backend.fahad288ali.workers.dev/v1/billing/paddle-webhook"

# First list event types
event_types_res = paddle_req("event-types")
events = [e["name"] for e in event_types_res.get("data", [])]
print(f"Available Event Types count: {len(events)}")
subscribed = [e for e in events if e.startswith("subscription.") or e.startswith("transaction.")]
print(f"Subscribed events count: {len(subscribed)}")

body = {
    "description": "VidRank Cloudflare Backend Webhook",
    "destination": webhook_url,
    "type": "url",
    "subscribed_events": [{"event_type_name": ev} for ev in subscribed]
}

res = paddle_req("notification-settings", method="POST", body=body)
print("\nNotification Settings Creation Result:")
print(json.dumps(res, indent=2))
