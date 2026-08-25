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

event_types_res = paddle_req("event-types")
raw_events = event_types_res.get("data", [])
print("First 5 raw events:", raw_events[:5])

# Try subscribed_events as list of dicts with `name` or string names
webhook_url = "https://vidrank-backend.fahad288ali.workers.dev/v1/billing/paddle-webhook"

body1 = {
    "description": "VidRank Backend Webhook",
    "destination": webhook_url,
    "type": "url",
    "subscribed_events": raw_events[:3] # pass full event dicts
}

res1 = paddle_req("notification-settings", method="POST", body=body1)
print("\nTest with full dicts:", json.dumps(res1, indent=2))
