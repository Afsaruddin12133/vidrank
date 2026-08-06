#!/usr/bin/env python3
"""
Verify Firebase token using YOUR BACKEND's Firebase verification
This uses the same code your backend uses!
"""

import sys
sys.path.insert(0, '/Users/macm1/Desktop/vidrank/backend')

from app import firebase
import asyncio

async def verify_user(token):
    """Verify Firebase token using backend's firebase module"""
    
    print("🔍 Verifying Firebase Authentication")
    print("=" * 60)
    
    # Mock env object (like backend uses)
    class MockEnv:
        AUTH_PROJECT_ID = None  # Will use default "vidrank" or you can set it
    
    env = MockEnv()
    
    try:
        print("🔐 Verifying token with Firebase...\n")
        claims = await firebase.verify_token(token, env)
        
        print("✅ USER IS AUTHENTICATED!\n")
        print("👤 User Information:")
        print(f"   UID:    {claims.get('uid')}")
        print(f"   Email:  {claims.get('email')}")
        print(f"   Name:   {claims.get('name', 'N/A')}")
        print(f"   Email Verified: {claims.get('email_verified', False)}")
        
        print(f"\n🔑 Token Details:")
        print(f"   Audience (Project ID): {claims.get('aud')}")
        print(f"   Issuer: {claims.get('iss')}")
        
        print(f"\n💡 Add to backend/.dev.vars:")
        print(f'AUTH_PROJECT_ID="{claims.get("aud")}"')
        
        return claims
        
    except firebase.AuthError as e:
        print(f"❌ Authentication failed: {e}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 check_firebase_auth.py YOUR_ID_TOKEN")
        print("\nGet token from DevTools Console:")
        print("localStorage.getItem('firebase:authUser:...')['stsTokenManager']['accessToken']")
        sys.exit(1)
    
    token = sys.argv[1].strip()
    asyncio.run(verify_user(token))
