import os
#!/usr/bin/env python3
import json
import urllib.request

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
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

all_events = [
    "subscription.created",
    "subscription.activated",
    "subscription.updated",
    "subscription.canceled",
    "subscription.past_due",
    "subscription.paused",
    "subscription.resumed",
    "subscription.imported",
    "transaction.completed",
    "transaction.paid",
    "transaction.billed",
    "transaction.canceled",
    "transaction.created",
    "transaction.ready"
]

res = paddle_req("notification-settings/ntfset_01m0tb412sgzbtww3qw56sqyp0", method="PATCH", body={
    "subscribed_events": all_events
})
print("Updated Subscribed Events:", len(res.get("data", {}).get("subscribed_events", [])))
