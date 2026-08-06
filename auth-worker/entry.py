"""VIDRANK auth service worker — verifies Firebase ID tokens via the Firebase
Admin SDK and serves the result to the main API worker over a service binding.

The main worker (vidrank-backend) calls this service with a POST body of
{"token": "<firebase id token>"} and receives either:
  - 200 {"ok": true, "claims": {...}}
  - 401 {"ok": false, "code": "token_expired" | "unauthorized", "detail": "..."}
"""
from __future__ import annotations

import json

from workers import WorkerEntrypoint  # type: ignore
from workers.response import Response

import firebase_admin
from firebase_admin import auth, credentials

# initialize_app() requires a credential even though ID-token verification only
# fetches Google's public certs by project_id (never signs). Dummy account, real
# RSA key, never used to sign anything.
_CERT = {
    "type": "service_account",
    "project_id": "vidrank-5e540",
    "private_key_id": "dummy-key-id-0000",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEogIBAAKCAQEAyr0V7kmIG1PxQz310B1WqXwAKcJUUq8CCJQonHS9kuSvqDZm\nhqo7IoWNzDUMr9fru/50YFoJt1+x/i7x619RgHpj/j1fVCUnB4pRY6wfjMPSSSPn\n9g6sZgD1wR30HP0p5HnjcRJOZtXsmKGs9szzcaGTu0PeuugzeR5swXsHv0XDU4OF\n98uBYlWgafOsdosxCEqSv8V3ce3ie8shHvnQELzhOgNAEBLVTtIf7VV3xxJuWM7B\npyr54TH7QQOYK7dzx4ax6NZrWGgaBGkgqjM8dvSklmUHQHPqWCBngTeWT7bX1uGq\nEIQGfn7cruiXewGKdmUmAdrSjWjgr7SvwmirUQIDAQABAoIBADNhQkqWhhDu8Cjr\nbf2lQc5IJ75tinM9+RT1f2lPSLAOltnZl5gvUjdIg4wqMaHq5cpKDXJRvz6i2Pgj\nK5pMGNqnqenH4f3wQHjvu/q3p3NEOWnh2KqKQ3TCb4XWsoQaQOCvZ03Dpuz28DQq\nXSxa+qNkoI0IAU17BXh/lm5eYLM/Zi626p8yVsLQdY4JR+LG+IvXXDcypVPqId1m\nI4zlXO1flW6r57sFV8ev+xR34X1WgYFOZVi634ude0GBUH2KXn+T0rs2lSgaRuNb\n2E+vBu8X6SJ8JeinwQBih9NjMBNkRNxarHUolS0VlZfwEI5opRXN6kAyLb3HLDEt\n5hXrmeUCgYEA8xdytwbUWj72ZrN4mR1xqnkJ2Rh36e6ykHXXqCjXfjqUlc/0V5E+\n1XPKxJ9L9VKL3oQbtJWd1/jhGUjJsHkXgn0wNN0szEfKcVxdyVhkA22Su0BGSLhb\n969O2ejrOe1aBSwLmnlGuZQwFapiPXARKtoSv3BrLonbUw6EApOVqNcCgYEA1YEV\nxCplZ7PGrIzGWwDz/TrN/M0BjpU6NsuMxjZosx04a4A7mcPo12E0mS6z09l/mPFq\nfY2YKgXVAfu7TM+6MNsUWFiKGGs9U11a/KKCKXuVDKRqWyJTFCaFgB/7S4dNk0NA\nF5PVHdkcMiHclOoTG4XlPhs9dLIUU+6gFHhtgBcCgYBRiUXi+hl0A7ZmEECdKvEb\nOuoAtWJTRssCBWTGdJyDLGb2MQBF9uPaeLJEbSHvMTbU9f7M/XoqHMJz1qQ/2v31\nuMPYl28VPec7Sr3ycQFq3O/getiYP64pT9Xk5Wkwztno7jMeJxt/16KhQbsd3F8F\nvouXRr/MplS4cR/6NUJ3lQKBgBDUYhDafq/T/f8wAZq+0nzNm9snlc3VeYdEOE6P\nj2U/Eml27DvMs5f2s5y3j7lNVb+KmChZdvspBodnfnYpkbW0L0BfilMucOEXZMqx\nTK1UboVWmIOiiwX1m2RkIPztJ3JKRM0W/B+kM5LIFIkwgl0TCuUAZLHEL9IF51x1\nubv1AoGAWNZsoirCL4yu8D+zoRNlVdBZXCZzZTlvC2ctp8M6I9ZmBr2bbqq7E1iI\n4SLCxSKrQH1MWH0+lKfus3irsE+M94U84Y1qe51jJWbEMHMV0WKyk5p+CbqToDxN\nn6w8KSvsDrNNhH7fltCG3aWcal2C7kkn1WvNkJm0QIOC40o0URs=\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "auth@vidrank-5e540.iam.gserviceaccount.com",
    "client_id": "100000000000000000000",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/auth%40vidrank-5e540.iam.gserviceaccount.com",
}
_app = None


def _get_app(env):
    global _app
    if _app is None and not firebase_admin._apps:
        _app = firebase_admin.initialize_app(
            credentials.Certificate(_CERT),
            options={"projectId": getattr(env, "AUTH_PROJECT_ID", None)})
    return _app


def _claims_payload(claims: dict) -> dict:
    # Only pass through fields the API needs — keeps the payload small and
    # avoids serialization issues with non-JSON types in the claims dict.
    keys = ("uid", "email", "email_verified", "name", "picture", "admin", "role")
    return {k: claims.get(k) for k in keys if k in claims}


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        _get_app(self.env)
        try:
            body = json.loads((await request.text()) or "{}")
        except Exception:
            body = {}
        token = body.get("token") or ""

        if not token:
            return self._reject("unauthorized", "missing token")

        try:
            claims = auth.verify_id_token(token)
            print(f"[auth] verified uid={claims.get('uid')} email={claims.get('email')}", flush=True)
            return Response(
                json.dumps({"ok": True, "claims": _claims_payload(claims)}),
                headers={"Content-Type": "application/json"},
            )
        except ValueError as e:
            # This SDK version raises plain ValueError for all failure modes;
            # expired/revoked tokens are signaled via the message text.
            msg = str(e)
            if "expired" in msg or "revoked" in msg:
                return self._reject("token_expired", msg)
            print(f"[auth] verify failed: {msg}", flush=True)
            return self._reject("unauthorized", msg)
        except Exception as e:
            print(f"[auth] verify failed: {e}", flush=True)
            return self._reject("unauthorized", str(e))

    def _reject(self, code: str, detail: str) -> Response:
        return Response(
            json.dumps({"ok": False, "code": code, "detail": detail}),
            status=401,
            headers={"Content-Type": "application/json"},
        )
