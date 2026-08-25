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

print(f"🚀 1. Adding destination address {friend_email} to Cloudflare account...")
dest_add = cf_api(f"accounts/{account_id}/email/routing/addresses", method="POST", body={"email": friend_email})
print("   Response:", json.dumps(dest_add, indent=2))

# List destination addresses
dests = cf_api(f"accounts/{account_id}/email/routing/addresses").get("result", [])
print(f"\n📬 Verified/Pending destination addresses on account:")
for d in dests:
    print(f"   • {d.get('email')} — status: {d.get('status')} (verified: {d.get('verified')})")

print(f"\n📋 2. Updating Email Routing Rules for vidrank.tech to route to BOTH recipients...")
# Fetch existing rules
rules_res = cf_api(f"zones/{zone_id}/email/routing/rules")
existing_rules = rules_res.get("result", [])

target_emails = [admin_email, friend_email]

rules_to_update = [
    {
        "name": "Forward support to team (Fahad & Tamim)",
        "enabled": True,
        "matchers": [
            {"type": "literal", "field": "to", "value": "support@vidrank.tech"}
        ],
        "actions": [
            {"type": "forward", "value": target_emails}
        ]
    },
    {
        "name": "Forward privacy to team (Fahad & Tamim)",
        "enabled": True,
        "matchers": [
            {"type": "literal", "field": "to", "value": "privacy@vidrank.tech"}
        ],
        "actions": [
            {"type": "forward", "value": target_emails}
        ]
    }
]

for rule in rules_to_update:
    rule_val = rule["matchers"][0]["value"]
    matching = next((r for r in existing_rules if any(m.get("value") == rule_val for m in r.get("matchers", []))), None)
    if matching:
        print(f"   ✓ Updating rule for {rule_val}...")
        res = cf_api(f"zones/{zone_id}/email/routing/rules/{matching['id']}", method="PUT", body=rule)
        print(f"     Success: {res.get('success')}")
        if not res.get("success"):
            print("     Details:", res.get("errors") or res)
    else:
        print(f"   + Creating rule for {rule_val}...")
        res = cf_api(f"zones/{zone_id}/email/routing/rules", method="POST", body=rule)
        print(f"     Success: {res.get('success')}")
        if not res.get("success"):
            print("     Details:", res.get("errors") or res)

print("\n✨ Done!")
