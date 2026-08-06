#!/usr/bin/env python3
"""Sync Firebase Firestore users to D1 using REST API."""
import json
import urllib.request
import urllib.error
import sqlite3
import os
import time

# Firebase config
FIREBASE_CONFIG = {
    "apiKey": "AIzaSyAlRH6242b-yDFn5E9yfyIwof6LsL7nWp8",
    "projectId": "vidrank-5e540",
}

FIRESTORE_BASE = f"https://firestore.googleapis.com/v1/projects/{FIREBASE_CONFIG['projectId']}/databases/(default)"


def fetch_firestore_users():
    """Fetch all users from Firestore users collection."""
    print("🔥 Fetching users from Firebase Firestore...")
    
    all_users = []
    page_token = None
    page = 1
    
    while True:
        url = f"{FIRESTORE_BASE}/documents/users?pageSize=500"
        if page_token:
            url += f"&pageToken={page_token}"
        
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "vidrank-sync",
                "X-Goog-Api-Key": FIREBASE_CONFIG['apiKey']
            })
            
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
                
                # Check for next page
                page_token = data.get('nextPageToken')
                if not page_token:
                    break
                    
                page += 1
                
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print("   ℹ️  Users collection not found or empty")
                break
            else:
                print(f"   ❌ HTTP Error {e.code}: {e.read().decode()}")
                break
        except Exception as e:
            print(f"   ❌ Error: {e}")
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
    print(f"\n📊 Final counts:")
    print(f"   Total: {total}")
    print(f"   Free:  {breakdown.get('free', 0)}")
    print(f"   Pro:   {breakdown.get('pro', 0)}")


def main():
    print("=" * 60)
    print("Firebase → D1 User Sync")
    print("=" * 60)
    print()
    
    # Fetch users from Firestore
    users = fetch_firestore_users()
    
    if not users:
        print("\n⚠️  No users found in Firestore")
        return
    
    print(f"\n✅ Fetched {len(users)} users from Firestore")
    
    # Show sample
    if users:
        print("\n📋 Sample users:")
        for i, u in enumerate(users[:3], 1):
            print(f"   {i}. {u['email']} ({u['tier']})")
        if len(users) > 3:
            print(f"   ... and {len(users) - 3} more")
    
    # Sync to D1
    sync_to_d1(users)
    
    print("\n✅ Sync complete! Refresh your dashboard to see updated user count.")
    print()


if __name__ == "__main__":
    main()
