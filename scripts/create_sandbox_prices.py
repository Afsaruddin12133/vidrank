import os
#!/usr/bin/env python3
"""Create all prices for existing sandbox products using correct override schema."""
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

TRIAL = {"interval": "day", "frequency": 7}

# Products already created
PLANS = [
    {
        "name": "Starter",
        "product_id": "pro_01m0tddygfw76hhxhm352h3kgn",
        "monthly_usd": "1000",
        "yearly_usd":  "10000",
        "overrides": {
            "monthly": [
                {"country_codes": ["GB"], "unit_price": {"amount": "800",  "currency_code": "GBP"}},
                {"country_codes": ["IE"], "unit_price": {"amount": "900",  "currency_code": "EUR"}},
                {"country_codes": ["AU"], "unit_price": {"amount": "1500", "currency_code": "AUD"}},
            ],
            "yearly": [
                {"country_codes": ["GB"], "unit_price": {"amount": "8000",  "currency_code": "GBP"}},
                {"country_codes": ["IE"], "unit_price": {"amount": "9000",  "currency_code": "EUR"}},
                {"country_codes": ["AU"], "unit_price": {"amount": "15000", "currency_code": "AUD"}},
            ],
        }
    },
    {
        "name": "Pro",
        "product_id": "pro_01m0tde06kt79rs90yxfx1kpz6",
        "monthly_usd": "4000",
        "yearly_usd":  "40000",
        "overrides": {
            "monthly": [
                {"country_codes": ["GB"], "unit_price": {"amount": "3200",  "currency_code": "GBP"}},
                {"country_codes": ["IE"], "unit_price": {"amount": "3600",  "currency_code": "EUR"}},
                {"country_codes": ["AU"], "unit_price": {"amount": "6000",  "currency_code": "AUD"}},
            ],
            "yearly": [
                {"country_codes": ["GB"], "unit_price": {"amount": "32000", "currency_code": "GBP"}},
                {"country_codes": ["IE"], "unit_price": {"amount": "36000", "currency_code": "EUR"}},
                {"country_codes": ["AU"], "unit_price": {"amount": "60000", "currency_code": "AUD"}},
            ],
        }
    },
    {
        "name": "Advanced",
        "product_id": "pro_01m0tde1wxr1vyb9r2ky9bf9xq",
        "monthly_usd": "12000",
        "yearly_usd":  "120000",
        "overrides": {
            "monthly": [
                {"country_codes": ["GB"], "unit_price": {"amount": "9500",   "currency_code": "GBP"}},
                {"country_codes": ["IE"], "unit_price": {"amount": "10800",  "currency_code": "EUR"}},
                {"country_codes": ["AU"], "unit_price": {"amount": "18000",  "currency_code": "AUD"}},
            ],
            "yearly": [
                {"country_codes": ["GB"], "unit_price": {"amount": "95000",  "currency_code": "GBP"}},
                {"country_codes": ["IE"], "unit_price": {"amount": "108000", "currency_code": "EUR"}},
                {"country_codes": ["AU"], "unit_price": {"amount": "180000", "currency_code": "AUD"}},
            ],
        }
    },
]

results = []

print("=" * 70)
print("PADDLE SANDBOX — CREATING PRICES (correct schema)")
print("=" * 70)

for plan in PLANS:
    print(f"\n{'─' * 60}")
    print(f"▶ {plan['name']} (product: {plan['product_id']})")

    # Monthly
    mo_body = {
        "product_id": plan["product_id"],
        "description": f"{plan['name']} Monthly",
        "unit_price": {"amount": plan["monthly_usd"], "currency_code": "USD"},
        "billing_cycle": {"interval": "month", "frequency": 1},
        "trial_period": TRIAL,
        "unit_price_overrides": plan["overrides"]["monthly"]
    }
    mo_res = paddle_req("prices", method="POST", body=mo_body)
    mo_data = mo_res.get("data", {})
    mo_id = mo_data.get("id")
    if mo_id:
        amt = int(plan["monthly_usd"]) / 100
        print(f"  ✓ Monthly  → {mo_id}  (USD ${amt:.2f}/mo, 7-day trial, 3 overrides)")
    else:
        print(f"  ✗ Monthly FAILED: {json.dumps(mo_res.get('error', mo_res))[:300]}")
    time.sleep(0.4)

    # Yearly
    yr_body = {
        "product_id": plan["product_id"],
        "description": f"{plan['name']} Annual",
        "unit_price": {"amount": plan["yearly_usd"], "currency_code": "USD"},
        "billing_cycle": {"interval": "year", "frequency": 1},
        "trial_period": TRIAL,
        "unit_price_overrides": plan["overrides"]["yearly"]
    }
    yr_res = paddle_req("prices", method="POST", body=yr_body)
    yr_data = yr_res.get("data", {})
    yr_id = yr_data.get("id")
    if yr_id:
        amt = int(plan["yearly_usd"]) / 100
        print(f"  ✓ Annual   → {yr_id}  (USD ${amt:.2f}/yr, 7-day trial, 3 overrides)")
    else:
        print(f"  ✗ Annual FAILED: {json.dumps(yr_res.get('error', yr_res))[:300]}")
    time.sleep(0.4)

    results.append({
        "plan": plan["name"],
        "product_id": plan["product_id"],
        "monthly_price_id": mo_id,
        "yearly_price_id": yr_id,
    })

# ─────────────────────────────────────────────────────────────────────────────
# Final summary
# ─────────────────────────────────────────────────────────────────────────────
print("\n\n" + "=" * 70)
print("COMPLETE CATALOG — ALL IDs")
print("=" * 70)
for r in results:
    print(f"\n  ┌─ {r['plan']}")
    print(f"  │  Product ID:       {r['product_id']}")
    print(f"  │  Monthly Price ID: {r['monthly_price_id']}")
    print(f"  └─ Annual Price ID:  {r['yearly_price_id']}")

print("\n" + "─" * 70)
print("Country Price Overrides (per plan)")
print("─" * 70)
overrides_table = [
    ("Starter",  "GB", "GBP", "£8.00/mo",   "£80.00/yr"),
    ("Starter",  "IE", "EUR", "€9.00/mo",   "€90.00/yr"),
    ("Starter",  "AU", "AUD", "A$15.00/mo", "A$150.00/yr"),
    ("Pro",      "GB", "GBP", "£32.00/mo",  "£320.00/yr"),
    ("Pro",      "IE", "EUR", "€36.00/mo",  "€360.00/yr"),
    ("Pro",      "AU", "AUD", "A$60.00/mo", "A$600.00/yr"),
    ("Advanced", "GB", "GBP", "£95.00/mo",  "£950.00/yr"),
    ("Advanced", "IE", "EUR", "€108.00/mo", "€1,080.00/yr"),
    ("Advanced", "AU", "AUD", "A$180.00/mo","A$1,800.00/yr"),
]
print(f"  {'Plan':<12} {'CC':<4} {'Currency':<10} {'Monthly':<14} {'Annual'}")
print(f"  {'─'*12} {'─'*4} {'─'*10} {'─'*14} {'─'*14}")
for row in overrides_table:
    print(f"  {row[0]:<12} {row[1]:<4} {row[2]:<10} {row[3]:<14} {row[4]}")
print("=" * 70)
