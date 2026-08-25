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

worker_js = """
export default {
  async email(message, env, ctx) {
    const recipients = ["fahad288ali@gmail.com", "itstamim.ban@gmail.com"];
    for (const to of recipients) {
      try {
        await message.forward(to);
      } catch (e) {
        console.error("Failed to forward to", to, e);
      }
    }
  }
};
"""

# Upload worker script
script_name = "vidrank-email-router"
url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/workers/scripts/{script_name}"
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/javascript"
}
req = urllib.request.Request(url, data=worker_js.encode("utf-8"), headers=headers, method="PUT")
try:
    with urllib.request.urlopen(req) as resp:
        print("Worker upload:", resp.read().decode("utf-8"))
except Exception as e:
    print("Worker upload err:", e)

# Now update rule for support@vidrank.tech to use worker action
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

rules = cf_api(f"zones/{zone_id}/email/routing/rules").get("result", [])
support_rule = next((r for r in rules if any(m.get("value") == "support@vidrank.tech" for m in r.get("matchers", []))), None)

if support_rule:
    updated_rule = {
        "name": "Forward support to Fahad & Tamim via Worker",
        "enabled": True,
        "matchers": [{"type": "literal", "field": "to", "value": "support@vidrank.tech"}],
        "actions": [{"type": "worker", "value": [script_name]}]
    }
    res = cf_api(f"zones/{zone_id}/email/routing/rules/{support_rule['id']}", method="PUT", body=updated_rule)
    print("Rule update result:", json.dumps(res, indent=2))

privacy_rule = next((r for r in rules if any(m.get("value") == "privacy@vidrank.tech" for m in r.get("matchers", []))), None)
if privacy_rule:
    updated_privacy = {
        "name": "Forward privacy to Fahad & Tamim via Worker",
        "enabled": True,
        "matchers": [{"type": "literal", "field": "to", "value": "privacy@vidrank.tech"}],
        "actions": [{"type": "worker", "value": [script_name]}]
    }
    res2 = cf_api(f"zones/{zone_id}/email/routing/rules/{privacy_rule['id']}", method="PUT", body=updated_privacy)
    print("Privacy rule update result:", json.dumps(res2, indent=2))
