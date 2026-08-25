import os
#!/usr/bin/env python3
import hmac
import hashlib
import json
import time
import urllib.request
import urllib.error

SECRET = os.environ.get("PADDLE_API_KEY", "")
URL = "https://vidrank-backend.fahad288ali.workers.dev/v1/billing/paddle-webhook"

def make_request(payload: dict, secret: str = SECRET, tamper_body: bool = False, tamper_sig: bool = False):
    raw_body = json.dumps(payload).encode("utf-8")
    ts = int(time.time())
    
    signed_payload = f"{ts}:{raw_body.decode('utf-8')}".encode("utf-8")
    h1 = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    
    if tamper_sig:
        h1 = "badhash" + h1[7:]
    
    send_body = raw_body if not tamper_body else raw_body + b"tampered"
    
    req = urllib.request.Request(
        URL,
        data=send_body,
        headers={
            "Paddle-Signature": f"ts={ts};h1={h1}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Paddle-Webhook-Simulator)"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        return 0, str(e)

print("🧪 1. Testing Invalid Signature (expect 400)...")
code, res = make_request({"event_type": "subscription.created", "event_id": "test_bad"}, tamper_sig=True)
print(f"Status: {code} | Response: {res}")
assert code == 400, f"Expected 400, got {code}"
print("   ✓ Correctly rejected with 400")

print("\n🧪 2. Testing Customer Created Event...")
cust_payload = {
    "event_id": f"evt_cust_{int(time.time())}",
    "event_type": "customer.created",
    "data": {
        "id": "ctm_sandbox_test_user_001",
        "email": "fahad288ali@gmail.com",
        "name": "Fahad Ali"
    }
}
code, res = make_request(cust_payload)
print(f"Status: {code} | Response: {res}")
assert code == 200, f"Expected 200, got {code}"
print("   ✓ Customer upsert processed")

print("\n🧪 3. Testing Subscription Created (Trialing -> Pro Access)...")
sub_payload = {
    "event_id": f"evt_sub_{int(time.time())}",
    "event_type": "subscription.created",
    "data": {
        "id": "sub_sandbox_test_001",
        "customer_id": "ctm_sandbox_test_user_001",
        "status": "trialing",
        "items": [
            {
                "price": {
                    "id": "pri_01m0tgszay6b67fxzmkmrxfkkv",
                    "product_id": "pro_01m0tgsyma0pj9t64b26gesm9w"
                }
            }
        ],
        "current_billing_period": {
            "starts_at": "2026-08-25T00:00:00Z",
            "ends_at": "2026-09-01T00:00:00Z"
        },
        "custom_data": {
            "email": "fahad288ali@gmail.com"
        }
    }
}
code, res = make_request(sub_payload)
print(f"Status: {code} | Response: {res}")
assert code == 200, f"Expected 200, got {code}"
print("   ✓ Subscription processed and access granted")

print("\n🎉 ALL WEBHOOK INTEGRATION TESTS PASSED!")
