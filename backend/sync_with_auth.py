#!/usr/bin/env python3
"""Sync Firebase users using Service Account authentication."""
import json
import urllib.request
import urllib.error
import sqlite3
import os
import time
import base64
import hashlib
import hmac

SERVICE_ACCOUNT_PATH = "serviceAccount.json"


def load_service_account():
    """Load service account credentials."""
    with open(SERVICE_ACCOUNT_PATH) as f:
        return json.load(f)


def create_jwt(service_account):
    """Create a JWT for Google OAuth."""
    import datetime
    
    now = int(time.time())
    exp = now + 3600  # 1 hour
    
    header = {
        "alg": "RS256",
        "typ": "JWT"
    }
    
    claim_set = {
        "iss": service_account["client_email"],
        "scope": "https://www.googleapis.com/auth/datastore",
        "aud": "https://oauth2.googleapis.com/token",
        "iat": now,
        "exp": exp
    }
    
    # Encode header and claims
    header_b64 = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip('=')
    claims_b64 = base64.urlsafe_b64encode(json.dumps(claim_set).encode()).decode().rstrip('=')
    
    message = f"{header_b64}.{claims_b64}"
    
    # Sign with private key
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.backends import default_backend
    
    private_key = serialization.load_pem_private_key(
        service_account["private_key"].encode(),
        password=None,
        backend=default_backend()
    )
    
    signature = private_key.sign(
        message.encode(),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
    
    return f"{message}.{signature_b64}"


def get_access_token(service_account):
    """Get OAuth2 access token."""
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


def fetch_firestore_users(access_token, project_id):
    """Fetch all users from Firestore."""
    print("🔥 Fetching users from Firebase Firestore...")
    
    base_url = f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)"
    all_users = []
    page_token = None
    page = 1
    
    while True:
        url = f"{base_url}/documents/users?pageSize=500"
        if page_token:
            url += f"&pageToken={page_token}"
        
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "vidrank-sync"
        })
        
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                
                documents = data.get('documents', [])
                print(f"   Page {page}: {len(documents)} users")
                
                for doc in documents:
                    name = doc.get('name', '')
                    uid = name.rsplit('/', 1)[-1]
                    fields = doc.get('fields', {})
                    
                    user = {
                        'firebase_uid': uid,
                        'email': fields.get('email', {}).get('stringValue', ''),
                        'tier': fields.get('plan', {}).get('stringValue', 'free'),
                        'is_active': int(fields.get('isActive', {}).get('booleanValue', True)),
                        'balance': _get_int(fields, 'balance'),
                        'subscription_id': _get_str(fields, 'subscriptionId'),
                        'expires_at': _get_str(fields, 'expiresAt'),
                        'referred_by': _get_str(fields, 'referredBy'),
                        'referred_by_sub_id': _get_str(fields, 'referredBySubId'),
                        'usage_count': _get_int(fields, 'usageCount') or 0,
                        'last_usage_reset': _get_int(fields, 'lastUsageReset'),
                        'name': _get_str(fields, 'name') or '',
                        'photo_url': _get_str(fields, 'photoUrl'),
                    }
                    all_users.append(user)
                
                page_token = data.get('nextPageToken')
                if not page_token:
                    break
                    
                page += 1
                
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            print(f"   ❌ HTTP Error {e.code}: {error_body}")
            break
        except Exception as e:
            print(f"   ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            break
    
    return all_users


def _get_str(fields, key):
    """Extract string value from Firestore field."""
    return fields.get(key, {}).get('stringValue')


def _get_int(fields, key):
    """Extract integer value from Firestore field."""
    val = fields.get(key, {}).get('integerValue')
    return int(val) if val else None


def sync_to_d1(users):
    """Sync users to D1 database."""
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
    
    for user in users:
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO users (
                    firebase_uid, email, tier, is_active, synced_at,
                    balance, subscription_id, expires_at, referred_by,
                    referred_by_sub_id, usage_count, last_usage_reset,
                    name, photo_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user['firebase_uid'],
                user['email'],
                user['tier'],
                user['is_active'],
                now,
                user['balance'],
                user['subscription_id'],
                user['expires_at'],
                user['referred_by'],
                user['referred_by_sub_id'],
                user['usage_count'],
                user['last_usage_reset'],
                user['name'],
                user['photo_url'],
            ))
            synced += 1
        except Exception as e:
            print(f"   ⚠️  Failed to sync {user['email']}: {e}")
    
    conn.commit()
    
    # Get final counts
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]
    
    cursor.execute("SELECT tier, COUNT(*) FROM users GROUP BY tier")
    breakdown = dict(cursor.fetchall())
    
    conn.close()
    
    print(f"\n✅ Synced {synced} users to D1")
    print(f"\n📊 Final Database Stats:")
    print(f"   Total Users: {total}")
    print(f"   Free Tier:   {breakdown.get('free', 0)}")
    print(f"   Pro Tier:    {breakdown.get('pro', 0)}")
    
    return total


def main():
    print("=" * 70)
    print("Firebase → D1 User Sync (Service Account Authentication)")
    print("=" * 70)
    print()
    
    # Load service account
    print("🔑 Loading service account credentials...")
    service_account = load_service_account()
    print(f"   ✓ Project: {service_account['project_id']}")
    print(f"   ✓ Email: {service_account['client_email']}")
    
    # Get access token
    print("\n🔐 Getting OAuth2 access token...")
    try:
        access_token = get_access_token(service_account)
        print("   ✓ Access token obtained")
    except Exception as e:
        print(f"   ❌ Failed to get access token: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Fetch users
    print()
    users = fetch_firestore_users(access_token, service_account['project_id'])
    
    if not users:
        print("\n⚠️  No users found in Firestore")
        print("\nPossible reasons:")
        print("  - The 'users' collection is empty")
        print("  - Service account doesn't have read permissions")
        print("  - Collection name is different")
        return
    
    print(f"\n✅ Fetched {len(users)} users from Firestore")
    
    # Show sample
    if users:
        print("\n📋 Sample users:")
        for i, u in enumerate(users[:5], 1):
            tier_label = u['tier'].upper()
            print(f"   {i}. {u['email']:40s} [{tier_label}]")
        if len(users) > 5:
            print(f"   ... and {len(users) - 5} more")
    
    # Sync to D1
    total = sync_to_d1(users)
    
    print("\n" + "=" * 70)
    print("✅ SYNC COMPLETE!")
    print("=" * 70)
    print(f"\nRefresh your dashboard to see {total} users!")
    print()


if __name__ == "__main__":
    main()
