import os
#!/usr/bin/env python3
"""Create full Paddle sandbox product catalog with trials and country overrides."""
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
        err = e.read().decode("utf-8")
        try:
            return json.loads(err)
        except:
            return {"error": err}
    except Exception as e:
        return {"error": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# Catalog definition
# ─────────────────────────────────────────────────────────────────────────────
PLANS = [
    {
        "name": "Starter",
        "description": "Perfect for individuals and small creators getting started with YouTube SEO.",
        "monthly_usd": "1000",    # $10.00
        "yearly_usd":  "10000",   # $100.00
        "overrides": {
            # unit_price overrides per country code
            "GB": {"monthly": {"amount": "800",   "currency": "GBP"},  "yearly": {"amount": "8000",  "currency": "GBP"}},
            "IE": {"monthly": {"amount": "900",   "currency": "EUR"},  "yearly": {"amount": "9000",  "currency": "EUR"}},
            "AU": {"monthly": {"amount": "1500",  "currency": "AUD"},  "yearly": {"amount": "15000", "currency": "AUD"}},
        }
    },
    {
        "name": "Pro",
        "description": "For growing channels that need advanced analytics and unlimited optimisations.",
        "monthly_usd": "4000",    # $40.00
        "yearly_usd":  "40000",   # $400.00
        "overrides": {
            "GB": {"monthly": {"amount": "3200",  "currency": "GBP"},  "yearly": {"amount": "32000", "currency": "GBP"}},
            "IE": {"monthly": {"amount": "3600",  "currency": "EUR"},  "yearly": {"amount": "36000", "currency": "EUR"}},
            "AU": {"monthly": {"amount": "6000",  "currency": "AUD"},  "yearly": {"amount": "60000", "currency": "AUD"}},
        }
    },
    {
        "name": "Advanced",
        "description": "For agencies and power users managing multiple channels at scale.",
        "monthly_usd": "12000",   # $120.00
        "yearly_usd":  "120000",  # $1200.00
        "overrides": {
            "GB": {"monthly": {"amount": "9500",   "currency": "GBP"},  "yearly": {"amount": "95000",  "currency": "GBP"}},
            "IE": {"monthly": {"amount": "10800",  "currency": "EUR"},  "yearly": {"amount": "108000", "currency": "EUR"}},
            "AU": {"monthly": {"amount": "18000",  "currency": "AUD"},  "yearly": {"amount": "180000", "currency": "AUD"}},
        }
    },
]

TRIAL = {"interval": "day", "frequency": 7}

results = []

print("=" * 70)
print("PADDLE SANDBOX — CREATING PRODUCT CATALOG")
print("=" * 70)

for plan in PLANS:
    print(f"\n{'─' * 60}")
    print(f"▶ Creating product: {plan['name']}")

    # 1. Create product
    prod_res = paddle_req("products", method="POST", body={
        "name": plan["name"],
        "description": plan["description"],
        "tax_category": "standard"
    })
    prod = prod_res.get("data", {})
    prod_id = prod.get("id")
    if not prod_id:
        print(f"  ✗ Product creation failed: {json.dumps(prod_res)[:200]}")
        continue
    print(f"  ✓ Product created  → {prod_id}")

    # Helper to build country_price_overrides list
    def build_overrides(overrides, period):
        return [
            {
                "country_code": cc,
                "unit_price": {
                    "amount": v[period]["amount"],
                    "currency_code": v[period]["currency"]
                }
            }
            for cc, v in overrides.items()
        ]

    # 2. Monthly price
    monthly_body = {
        "product_id": prod_id,
        "description": f"{plan['name']} Monthly",
        "unit_price": {"amount": plan["monthly_usd"], "currency_code": "USD"},
        "billing_cycle": {"interval": "month", "frequency": 1},
        "trial_period": TRIAL,
        "unit_price_overrides": build_overrides(plan["overrides"], "monthly")
    }
    mo_res = paddle_req("prices", method="POST", body=monthly_body)
    mo = mo_res.get("data", {})
    mo_id = mo.get("id")
    if mo_id:
        print(f"  ✓ Monthly price    → {mo_id}  (USD ${int(plan['monthly_usd'])/100:.2f}/mo + 7-day trial)")
    else:
        print(f"  ✗ Monthly price failed: {json.dumps(mo_res)[:300]}")

    time.sleep(0.3)  # gentle rate-limit spacing

    # 3. Annual price
    yearly_body = {
        "product_id": prod_id,
        "description": f"{plan['name']} Annual",
        "unit_price": {"amount": plan["yearly_usd"], "currency_code": "USD"},
        "billing_cycle": {"interval": "year", "frequency": 1},
        "trial_period": TRIAL,
        "unit_price_overrides": build_overrides(plan["overrides"], "yearly")
    }
    yr_res = paddle_req("prices", method="POST", body=yearly_body)
    yr = yr_res.get("data", {})
    yr_id = yr.get("id")
    if yr_id:
        print(f"  ✓ Annual price     → {yr_id}  (USD ${int(plan['yearly_usd'])/100:.2f}/yr + 7-day trial)")
    else:
        print(f"  ✗ Annual price failed: {json.dumps(yr_res)[:300]}")

    results.append({
        "plan": plan["name"],
        "product_id": prod_id,
        "monthly_price_id": mo_id,
        "yearly_price_id": yr_id,
    })
    time.sleep(0.3)

# ─────────────────────────────────────────────────────────────────────────────
# Summary table
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("CATALOG COMPLETE — ID MAPPING")
print("=" * 70)
for r in results:
    print(f"\n  Plan: {r['plan']}")
    print(f"    Product ID:       {r['product_id']}")
    print(f"    Monthly Price ID: {r['monthly_price_id']}")
    print(f"    Annual Price ID:  {r['yearly_price_id']}")

print("\n" + "=" * 70)
print("Country Price Overrides Applied")
print("=" * 70)
headers = ["Plan", "Currency", "Monthly", "Annual"]
rows = []
for plan in PLANS:
    for cc, ovr in plan["overrides"].items():
        mo_amt = int(ovr["monthly"]["amount"]) / 100
        yr_amt = int(ovr["yearly"]["amount"]) / 100
        rows.append(f"  {plan['name']:10}  {cc}  {ovr['monthly']['currency']}  {mo_amt:.2f}/mo  {yr_amt:.2f}/yr")
for row in rows:
    print(row)
