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

zone_id = "9582c6cfdce17be14c1a1ed505b6c239"
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
        err = e.read().decode("utf-8")
        try:
            return json.loads(err)
        except:
            return {"success": False, "error": err}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Cloudflare Email Routing: If a custom address already has a rule, Cloudflare rules are unique by matcher, or can use Email Workers / subaddressing.
# Let's check how Cloudflare handles routing to multiple destinations or check existing rules
rules = cf_api(f"zones/{zone_id}/email/routing/rules").get("result", [])
print("Existing rules:")
for r in rules:
    print(r)

rule_body = {
    "name": "Tamim support forward",
    "enabled": True,
    "matchers": [{"type": "literal", "field": "to", "value": "support@vidrank.tech"}],
    "actions": [{"type": "forward", "value": [friend_email]}],
    "priority": 10
}

res = cf_api(f"zones/{zone_id}/email/routing/rules", method="POST", body=rule_body)
print("\nCreate rule response:", json.dumps(res, indent=2))
