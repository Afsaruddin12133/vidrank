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

print("🔍 Checking overall email routing status for vidrank.tech...")
status_res = cf_api(f"zones/{zone_id}/email/routing")
print("Status:", json.dumps(status_res.get("result", {}), indent=2))

# Check rules
rules = cf_api(f"zones/{zone_id}/email/routing/rules").get("result", [])
print("\nActive Email Rules:")
for r in rules:
    print(f"  • {r.get('name') or r.get('id')}: enabled={r.get('enabled')}, matchers={r.get('matchers')}, actions={r.get('actions')}")
