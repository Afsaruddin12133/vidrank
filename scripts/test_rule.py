#!/usr/bin/env python3
import os
import json
import urllib.request
import urllib.error

config_path = os.path.expanduser("~/.wrangler/config/default.toml")
token = None
with open(config_path, "r", encoding="utf-8") as f:
    for line in f:
        if "oauth_token" in line:
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

account_id = "888ad088a0b226524650478393ad1561"
zone_id = "9582c6cfdce17be14c1a1ed505b6c239"
admin_email = "fahad288ali@gmail.com"
friend_email = "itstamim.ban@gmail.com"

def cf_api(endpoint, method="GET", body=None):
    url = f"https://api.cloudflare.com/client/v4/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        try:
            return json.loads(err_body)
        except:
            return {"success": False, "error": err_body}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Try multiple actions first
multi_action_rule = {
    "name": "Forward support to Fahad & Tamim",
    "enabled": True,
    "matchers": [
        {"type": "literal", "field": "to", "value": "support@vidrank.tech"}
    ],
    "actions": [
        {"type": "forward", "value": [admin_email]},
        {"type": "forward", "value": [friend_email]}
    ]
}

print("Testing multiple actions in one rule...")
test_res = cf_api(f"zones/{zone_id}/email/routing/rules", method="POST", body=multi_action_rule)
print("Response:", test_res)

# Check all current rules
rules = cf_api(f"zones/{zone_id}/email/routing/rules").get("result", [])
print("\nCurrent Zone Rules:")
for r in rules:
    print(f" • {r.get('name') or r.get('id')}: matchers={r.get('matchers')}, actions={r.get('actions')}")
