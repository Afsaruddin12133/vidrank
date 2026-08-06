#!/usr/bin/env python3
"""Sync pricing from Firebase plans to D1 database."""
import json
import urllib.request
import urllib.error
import sqlite3
import os
import time

SERVICE_ACCOUNT_PATH = "serviceAccount.json"


def load_service_account():
    with open(SERVICE_ACCOUNT_PATH) as f:
        return json.load(f)


def create_jwt(service_account):
    import base64
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
    
    now = int(time.time())
    exp = now + 3600
    
    header = {"alg": "RS256", "typ": "JWT"}
    claim_set = {
        "iss": service_account["client_email"],
        "scope": "https://www.googleapis.com/auth/datastore",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": exp
    }
    
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
    claims_b64 = base64.urlsafe_b64encode(json.dumps(claim_set).encode()).decode().rstrip('=')
    message = f"{header_b64}.{claims_b64}"
    
    private_key = serialization.load_pem_private_key(
        service_account["private_key"].encode(),
        password=None,
        backend=default_backend()
    )
    
    signature = private_key.sign(message.encode(), padding.PKCS1v15(), hashes.SHA256())
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
    
    return f"{message}.{signature_b64}"


def get_access_token(service_account):
    jwt_token = create_jwt(service_account)
    data = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': jwt_token
    }).encode()
    
    req = urllib.request.Request(
        'https://oauth2.googleapis.com/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'}
    )
    
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        return result['access_token']


def fetch_firebase_plan(access_token, project_id, plan_id):
    base_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)"
    url = f"{base_url}/documents/plan/{plan_id}"
    
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {access_token}"
    })
    
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            fields = data.get('fields', {})
            
            # Extract values
            daily_limit_val = fields.get('dailyLimit', {}).get('integerValue')
            price_val = fields.get('price', {}).get('integerValue') or fields.get('price', {}).get('doubleValue')
            details = fields.get('plandetails', {}).get('stringValue', '')
            
            return {
                'plan_id': plan_id,
                'daily_limit': int(daily_limit_val) if daily_limit_val else None,
                'price': float(price_val) if price_val else 0,
                'plandetails': details
            }
    except urllib.error.HTTPError as e:
        print(f"   ⚠️  Plan '{plan_id}' not found in Firebase")
        return None


def sync_to_d1(plans):
    # Find D1 database
    db_dir = ".wrangler/state/v3/d1/miniflare-D1DatabaseObject"
    db_files = [f for f in os.listdir(db_dir) if f.endswith('.sqlite') and f != 'metadata.sqlite']
    
    if not db_files:
        print("❌ No D1 database found")
        return
    
    db_path = os.path.join(db_dir, db_files[0])
    print(f"\n💾 Syncing to D1: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    now = int(time.time())
    synced = 0
    
    for plan in plans:
        if not plan:
            continue
            
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO plans (
                    plan_id, daily_limit, synced_at, price, plandetails
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                plan['plan_id'],
                plan['daily_limit'],
                now,
                plan['price'],
                plan['plandetails']
            ))
            synced += 1
            print(f"   ✓ {plan['plan_id']}: ${plan['price']}/month, {plan['daily_limit']} req/day")
        except Exception as e:
            print(f"   ⚠️  Failed to sync {plan['plan_id']}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Synced {synced} plans to D1")


def main():
    print("=" * 70)
    print("Firebase Plans → D1 Pricing Sync")
    print("=" * 70)
    print()
    
    # Load service account
    print("🔑 Loading service account credentials...")
    service_account = load_service_account()
    print(f"   ✓ Project: {service_account['project_id']}")
    
    # Get access token
    print("\n🔐 Getting OAuth2 access token...")
    try:
        access_token = get_access_token(service_account)
        print("   ✓ Access token obtained")
    except Exception as e:
        print(f"   ❌ Failed to get access token: {e}")
        return
    
    # Fetch plans from Firebase
    print("\n🔥 Fetching plans from Firebase...")
    plans = []
    for plan_id in ['free', 'pro']:
        plan = fetch_firebase_plan(access_token, service_account['project_id'], plan_id)
        if plan:
            plans.append(plan)
            print(f"   ✓ {plan_id}: ${plan['price']}/month")
    
    if not plans:
        print("\n⚠️  No plans found in Firebase")
        return
    
    # Sync to D1
    sync_to_d1(plans)
    
    print("\n" + "=" * 70)
    print("✅ SYNC COMPLETE!")
    print("=" * 70)
    print("\nPricing is now dynamic from Firebase!")
    print("Dashboard will use actual Firebase pricing values.")
    print()


if __name__ == "__main__":
    main()
