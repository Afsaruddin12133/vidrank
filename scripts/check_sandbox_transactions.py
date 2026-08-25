import os
#!/usr/bin/env python3
import json
import urllib.request

API_KEY = os.environ.get("PADDLE_API_KEY", "")
BASE_URL = "https://sandbox-api.paddle.com"

req = urllib.request.Request(
    f"{BASE_URL}/transactions",
    headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    txs = data.get("data", [])
    print(f"Found {len(txs)} transaction(s) in sandbox:")
    for t in txs[:5]:
        print(" • ID:", t.get("id"), "| Status:", t.get("status"), "| Total:", t.get("details", {}).get("totals", {}).get("total"), t.get("currency_code"))
