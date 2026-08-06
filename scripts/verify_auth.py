#!/usr/bin/env python3
"""
Verify Firebase Authentication using Firebase Admin SDK
Run: pip install firebase-admin
"""

import firebase_admin
from firebase_admin import credentials, auth
import sys

print("🔍 Firebase Authentication Verification")
print("=" * 60)

# Initialize Firebase Admin SDK
# You need to download service account key from Firebase Console
try:
    cred = credentials.Certificate('path/to/serviceAccountKey.json')
    firebase_admin.initialize_app(cred)
    print("✅ Firebase Admin SDK initialized\n")
except Exception as e:
    print(f"⚠️  Using default credentials: {e}\n")

# Get token from command line
if len(sys.argv) < 2:
    print("Usage: python3 check_auth.py YOUR_ID_TOKEN")
    print("\nGet your token from browser:")
    print("1. Open DevTools (F12)")
    print("2. Console → Run: localStorage.getItem('firebase:authUser:...')")
    print("3. Copy the 'accessToken' value")
    sys.exit(1)

id_token = sys.argv[1]

# Verify the token
try:
    print("🔐 Verifying token with Firebase...")
    decoded_token = auth.verify_id_token(id_token)
    
    print("✅ TOKEN IS VALID!\n")
    print("👤 User Information:")
    print(f"   UID:    {decoded_token.get('uid')}")
    print(f"   Email:  {decoded_token.get('email')}")
    print(f"   Name:   {decoded_token.get('name', 'N/A')}")
    print(f"   Email Verified: {decoded_token.get('email_verified', False)}")
    
    print(f"\n🔑 Project ID: {decoded_token.get('aud')}")
    print(f"\n💡 Add to backend/.dev.vars:")
    print(f'AUTH_PROJECT_ID="{decoded_token.get("aud")}"')
    
except auth.InvalidIdTokenError:
    print("❌ Invalid token!")
except auth.ExpiredIdTokenError:
    print("❌ Token expired!")
except Exception as e:
    print(f"❌ Error: {e}")
