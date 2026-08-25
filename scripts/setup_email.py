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
zone_name = "vidrank.tech"
target_email = "fahad288ali@gmail.com"

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

print(f"📬 Creating/Updating Email Routing Rules for {zone_name}...")

# List existing rules
rules_res = cf_api(f"zones/{zone_id}/email/routing/rules")
existing_rules = rules_res.get("result", [])
print(f"   Existing rules: {len(existing_rules)}")
for r in existing_rules:
    print(f"   - Rule ID: {r.get('id')}, name: {r.get('name')}, matchers: {r.get('matchers')}, actions: {r.get('actions')}")

rules_to_create = [
    {
        "name": "support@vidrank.tech -> fahad288ali@gmail.com",
        "enabled": True,
        "matchers": [
            {"type": "literal", "field": "to", "value": "support@vidrank.tech"}
        ],
        "actions": [
            {"type": "forward", "value": [target_email]}
        ]
    },
    {
        "name": "privacy@vidrank.tech -> fahad288ali@gmail.com",
        "enabled": True,
        "matchers": [
            {"type": "literal", "field": "to", "value": "privacy@vidrank.tech"}
        ],
        "actions": [
            {"type": "forward", "value": [target_email]}
        ]
    }
]

for rule in rules_to_create:
    rule_val = rule["matchers"][0]["value"]
    # Check if existing
    matching = next((r for r in existing_rules if any(m.get("value") == rule_val for m in r.get("matchers", []))), None)
    if matching:
        print(f"   ✓ Updating existing rule for {rule_val}...")
        res = cf_api(f"zones/{zone_id}/email/routing/rules/{matching['id']}", method="PUT", body=rule)
        print(f"     Result: success={res.get('success')}")
    else:
        print(f"   + Creating new rule for {rule_val}...")
        res = cf_api(f"zones/{zone_id}/email/routing/rules", method="POST", body=rule)
        print(f"     Result: success={res.get('success')}")
        if not res.get("success"):
            print("     Error:", res.get("errors") or res)

# Check DNS settings on email routing
print(f"\n🔍 Checking Email Routing DNS status...")
dns_check = cf_api(f"zones/{zone_id}/email/routing/dns")
print("   DNS Status:", json.dumps(dns_check, indent=2))
