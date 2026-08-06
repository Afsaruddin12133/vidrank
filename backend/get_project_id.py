#!/usr/bin/env python3
"""Extract Firebase project ID from JWT token."""

import base64
import json
import sys


def decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without verification."""
    try:
        # JWT structure: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            print("❌ Invalid JWT format")
            return {}
        
        # Decode payload (add padding if needed)
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64 + padding)
        
        return json.loads(payload_json)
    except Exception as e:
        print(f"❌ Error decoding: {e}")
        return {}


if __name__ == "__main__":
    print("=" * 70)
    print("🔍 Firebase Project ID Finder")
    print("=" * 70)
    print()
    
    if len(sys.argv) > 1:
        # Token provided as argument
        token = sys.argv[1].strip()
    else:
        # Ask user to paste token
        print("Paste your Firebase ID token (from Authorization header):")
        print("(Or press Ctrl+C to cancel)")
        print()
        token = input("Token: ").strip()
    
    # Remove "Bearer " prefix if present
    if token.startswith("Bearer "):
        token = token[7:]
    
    print()
    print("Decoding token...")
    print()
    
    payload = decode_jwt_payload(token)
    
    if not payload:
        print("❌ Failed to decode token")
        sys.exit(1)
    
    print("✅ Token decoded successfully!")
    print()
    print("=" * 70)
    print("📋 TOKEN INFORMATION")
    print("=" * 70)
    print()
    
    # Extract key fields
    project_id = payload.get("aud", "")
    uid = payload.get("uid", "")
    email = payload.get("email", "")
    issuer = payload.get("iss", "")
    exp = payload.get("exp", 0)
    iat = payload.get("iat", 0)
    
    print(f"🔑 Project ID (aud):  {project_id}")
    print(f"👤 User ID (uid):     {uid}")
    print(f"📧 Email:             {email}")
    print(f"🔐 Issuer:            {issuer}")
    print(f"⏰ Issued at:         {iat}")
    print(f"⏰ Expires at:        {exp}")
    print()
    
    if project_id:
        print("=" * 70)
        print("✅ SOLUTION: Add this to backend/.dev.vars")
        print("=" * 70)
        print()
        print(f'AUTH_PROJECT_ID="{project_id}"')
        print()
        print("Then restart backend:")
        print("  cd backend")
        print("  uv run python dev_server.py")
        print()
    else:
        print("❌ No project ID found in token")
    
    print("=" * 70)
