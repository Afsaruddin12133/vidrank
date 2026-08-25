#!/usr/bin/env python3
"""Unit and verification test for Paddle Webhook signature verification and handlers."""
import hashlib
import hmac
import json
import time
import unittest


def verify_paddle_signature(raw_body: bytes, sig_header: str | None, secret_key: str) -> tuple[bool, str]:
    if not secret_key:
        return False, "Missing PADDLE_WEBHOOK_SECRET_KEY"
    if not sig_header:
        return False, "Missing Paddle-Signature header"

    parts = {}
    for item in sig_header.split(";"):
        if "=" in item:
            k, v = item.split("=", 1)
            parts[k.strip()] = v.strip()

    ts_str = parts.get("ts")
    h1 = parts.get("h1")
    if not ts_str or not h1:
        return False, "Malformed Paddle-Signature header"

    try:
        ts = int(ts_str)
    except ValueError:
        return False, "Invalid timestamp in Paddle-Signature"

    if abs(time.time() - ts) > 300:
        return False, f"Paddle webhook timestamp expired or drifted"

    signed_payload = f"{ts}:{raw_body.decode('utf-8')}".encode("utf-8")
    expected_h1 = hmac.new(secret_key.strip().encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_h1, h1):
        return False, "Invalid signature hash"

    return True, "ok"


class TestPaddleWebhookSecurity(unittest.TestCase):
    def setUp(self):
        self.secret = "mock_webhook_secret_for_tests_12345"
        self.sample_payload = json.dumps({
            "event_id": "evt_01test123",
            "event_type": "subscription.activated",
            "data": {
                "id": "sub_01live_test",
                "status": "active",
                "custom_data": {
                    "firebase_uid": "user_firebase_123",
                    "email": "creator@vidrank.ai"
                },
                "current_billing_period": {
                    "ends_at": "2026-09-24T12:00:00Z"
                }
            }
        }).encode("utf-8")

    def test_valid_signature(self):
        ts = int(time.time())
        signed_payload = f"{ts}:{self.sample_payload.decode('utf-8')}".encode("utf-8")
        h1 = hmac.new(self.secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        sig_header = f"ts={ts};h1={h1}"

        valid, reason = verify_paddle_signature(self.sample_payload, sig_header, self.secret)
        self.assertTrue(valid, f"Expected signature to be valid, got: {reason}")
        self.assertEqual(reason, "ok")

    def test_invalid_signature_hash(self):
        ts = int(time.time())
        sig_header = f"ts={ts};h1=0000000000000000000000000000000000000000000000000000000000000000"

        valid, reason = verify_paddle_signature(self.sample_payload, sig_header, self.secret)
        self.assertFalse(valid)
        self.assertEqual(reason, "Invalid signature hash")

    def test_replay_attack_expired_timestamp(self):
        # 10 minutes ago
        ts = int(time.time()) - 600
        signed_payload = f"{ts}:{self.sample_payload.decode('utf-8')}".encode("utf-8")
        h1 = hmac.new(self.secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        sig_header = f"ts={ts};h1={h1}"

        valid, reason = verify_paddle_signature(self.sample_payload, sig_header, self.secret)
        self.assertFalse(valid)
        self.assertIn("expired", reason)

    def test_tampered_payload(self):
        ts = int(time.time())
        signed_payload = f"{ts}:{self.sample_payload.decode('utf-8')}".encode("utf-8")
        h1 = hmac.new(self.secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        sig_header = f"ts={ts};h1={h1}"

        tampered_payload = self.sample_payload + b" "
        valid, reason = verify_paddle_signature(tampered_payload, sig_header, self.secret)
        self.assertFalse(valid)
        self.assertEqual(reason, "Invalid signature hash")


if __name__ == "__main__":
    unittest.main()
