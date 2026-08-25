#!/usr/bin/env python3
import os
import json
import urllib.request

config_path = os.path.expanduser("~/.wrangler/config/default.toml")
token = None
with open(config_path, "r", encoding="utf-8") as f:
    for line in f:
        if "oauth_token" in line:
            token = line.split("=", 1)[1].strip().strip('"').strip("'")
            break

account_id = "888ad088a0b226524650478393ad1561"
zone_id = "9582c6cfdce17be14c1a1ed505b6c239"

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
    except Exception as e:
        return {"success": False, "error": str(e)}

dests = cf_api(f"accounts/{account_id}/email/routing/addresses").get("result", [])
print("Current Destination Addresses:")
for d in dests:
    print(f" • {d.get('email')} -> status: {d.get('status')}, verified: {d.get('verified')}")

# Try adding Tamim rule if verified
tamim_dest = next((d for d in dests if d.get("email") == "itstamim.ban@gmail.com"), None)
if tamim_dest and tamim_dest.get("verified"):
    print("\n✓ Tamim is verified! Adding rules...")
    rule1 = {
        "name": "support@vidrank.tech -> itstamim.ban@gmail.com",
        "enabled": True,
        "matchers": [{"type": "literal", "field": "to", "value": "support@vidrank.tech"}],
        "actions": [{"type": "forward", "value": ["itstamim.ban@gmail.com"]}]
    }
    r1 = cf_api(f"zones/{zone_id}/email/routing/rules", method="POST", body=rule1)
    print("Support rule:", r1.get("success"))
else:
    print("\n⏳ Tamim has not clicked the verification link yet.")
