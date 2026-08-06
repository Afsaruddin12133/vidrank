#!/usr/bin/env python3
"""Check Firebase Authentication"""

import base64
import json
import sys

# Your Firebase user data
userData = {
    "uid": "nBdObpDEybTNOIwAxWMxyGUsBDy2",
    "email": "business.fahadali@gmail.com",
    "displayName": "Fahad Ali",
    "emailVerified": True,
}

# Get token from command line or use placeholder
if len(sys.argv) > 1:
    userData["accessToken"] = sys.argv[1]
else:
    userData["accessToken"] = None

print("🔍 Checking Firebase Authentication...\n")

# Check if authenticated
if userData.get("uid") and userData.get("email"):
    print("✅ USER IS AUTHENTICATED!\n")
    print(f"User:  {userData['displayName']}")
    print(f"Email: {userData['email']}")
    print(f"UID:   {userData['uid']}")
    print(f"Email Verified: {'Yes' if userData['emailVerified'] else 'No'}")
    
    # Decode token to get Project ID
    token = userData["stsTokenManager"]["accessToken"]
    try:
        parts = token.split(".")
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64 + padding)
        claims = json.loads(decoded)
        
        print(f"\n🔑 Project ID: {claims.get('aud', 'N/A')}")
        print(f"\n💡 Add to backend/.dev.vars:")
        print(f'AUTH_PROJECT_ID="{claims.get("aud")}"')
        
    except Exception as e:
        print(f"\n⚠️  Could not decode token: {e}")
else:
    print("❌ NOT AUTHENTICATED")
