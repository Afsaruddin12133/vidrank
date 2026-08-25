import os
#!/usr/bin/env python3
"""Probe correct unit_price_overrides schema, then create all prices."""
import json
import urllib.request
import urllib.error
import time

SANDBOX_API_KEY = os.environ.get("PADDLE_API_KEY", "")
BASE_URL = "https://sandbox-api.paddle.com"

def paddle_req(endpoint, method="GET", body=None):
    url = f"{BASE_URL}/{endpoint.lstrip('/')}"
    headers = {"Authorization": f"Bearer {SANDBOX_API_KEY}", "Content-Type": "application/json"}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return json.loads(e.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

# Use Starter product created earlier
STARTER_PROD = "pro_01m0tddygfw76hhxhm352h3kgn"

# Schema attempt 1: array of {countries: [...], unit_price: {...}}
print("Testing override schema v1: {countries: [...], unit_price: {...}}")
res1 = paddle_req("prices", method="POST", body={
    "product_id": STARTER_PROD,
    "description": "Schema test v1",
    "unit_price": {"amount": "1000", "currency_code": "USD"},
    "billing_cycle": {"interval": "month", "frequency": 1},
    "unit_price_overrides": [
        {
            "countries": ["GB"],
            "unit_price": {"amount": "800", "currency_code": "GBP"}
        }
    ]
})
if res1.get("data", {}).get("id"):
    print("  ✓ v1 works! Price ID:", res1["data"]["id"])
    # Clean it up by archiving
    pid = res1["data"]["id"]
    paddle_req(f"prices/{pid}", method="PATCH", body={"status": "archived"})
else:
    print("  ✗ v1 failed:", json.dumps(res1.get("error", res1))[:300])

    # Schema attempt 2: same but country_codes plural
    print("\nTesting override schema v2: {country_codes: [...], unit_price: {...}}")
    res2 = paddle_req("prices", method="POST", body={
        "product_id": STARTER_PROD,
        "description": "Schema test v2",
        "unit_price": {"amount": "1000", "currency_code": "USD"},
        "billing_cycle": {"interval": "month", "frequency": 1},
        "unit_price_overrides": [
            {
                "country_codes": ["GB"],
                "unit_price": {"amount": "800", "currency_code": "GBP"}
            }
        ]
    })
    if res2.get("data", {}).get("id"):
        print("  ✓ v2 works! Price ID:", res2["data"]["id"])
        pid = res2["data"]["id"]
        paddle_req(f"prices/{pid}", method="PATCH", body={"status": "archived"})
    else:
        print("  ✗ v2 failed:", json.dumps(res2.get("error", res2))[:300])

        # Schema attempt 3: no override, just base price (to confirm prices work without overrides)
        print("\nTesting with NO overrides at all")
        res3 = paddle_req("prices", method="POST", body={
            "product_id": STARTER_PROD,
            "description": "Schema test no overrides",
            "unit_price": {"amount": "1000", "currency_code": "USD"},
            "billing_cycle": {"interval": "month", "frequency": 1},
            "trial_period": {"interval": "day", "frequency": 7}
        })
        if res3.get("data", {}).get("id"):
            print("  ✓ No overrides works. Price ID:", res3["data"]["id"])
            # Get the full response to see what override format is returned
            pid = res3["data"]["id"]
            detail = paddle_req(f"prices/{pid}")
            print("  Full price object keys:", list(detail.get("data", {}).keys()))
            print("  unit_price_overrides field:", detail.get("data", {}).get("unit_price_overrides"))
            paddle_req(f"prices/{pid}", method="PATCH", body={"status": "archived"})
        else:
            print("  ✗ No-override also failed:", json.dumps(res3.get("error", res3))[:300])
