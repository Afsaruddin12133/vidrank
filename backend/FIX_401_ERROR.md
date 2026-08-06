# 🔴 FIX: 401 Error on Login

## 🎯 Problem Found!

Your backend is rejecting the Firebase token because **`AUTH_PROJECT_ID` is not configured**.

### What's Happening:

```python
# backend/app/firebase.py line 93:
project_id = getattr(env, "AUTH_PROJECT_ID", "") or "vidrank"
if claims.get("aud") != project_id:
    raise AuthError("wrong audience")  # ← 401 error here!
```

The backend expects your Firebase project ID, but it's not set, so it defaults to `"vidrank"`.

Your actual Firebase project ID is **different**, so token verification fails → 401 error.

---

## ✅ Solution (2 Steps)

### Step 1: Get Your Firebase Project ID

**Option A: From Network Request (DevTools)**

1. In your screenshot, you have the Authorization header with a JWT token
2. Run this script to extract the project ID:

```bash
cd /Users/macm1/Desktop/vidrank/backend
python3 get_project_id.py
```

3. When prompted, paste the **entire token** from Authorization header (the long string after "Bearer ")

**Option B: From Firebase Console**

1. Go to https://console.firebase.google.com/
2. Select your VidRank project
3. Click ⚙️ (Settings) → Project settings
4. Copy the **Project ID** (not Project name!)

**Option C: From IndexedDB**

Your screenshot showed IndexedDB. The token there contains the project ID.

1. Open DevTools → Application → IndexedDB
2. Find your Firebase token
3. Copy the full `accessToken` value
4. Run: `python3 get_project_id.py "YOUR_TOKEN_HERE"`

---

### Step 2: Configure Backend

Once you have your Firebase Project ID (e.g., `vidrank-abc123`):

**Create or update `.dev.vars` file:**

```bash
cd /Users/macm1/Desktop/vidrank/backend

# Create .dev.vars with your project ID
cat > .dev.vars << 'EOF'
AUTH_PROJECT_ID="your-firebase-project-id-here"
JWT_SECRET="your-jwt-secret-here"
ENCRYPTION_KEY="your-32-byte-encryption-key-here"
EOF
```

Replace `"your-firebase-project-id-here"` with your actual project ID.

**Restart backend:**

```bash
# Stop current backend (Ctrl+C if running)
# Start again
uv run python dev_server.py
```

---

## 🧪 Test It Works

After adding `AUTH_PROJECT_ID` and restarting:

**Test 1: Check .dev.vars exists**
```bash
cd /Users/macm1/Desktop/vidrank/backend
cat .dev.vars
# Should show: AUTH_PROJECT_ID="your-project-id"
```

**Test 2: Try login again**
1. Click VidRank extension icon
2. Click "Sign in with Google"
3. Check DevTools Network tab
4. Should now see **200 OK** instead of 401!

**Test 3: Verify user in database**
```bash
cd /Users/macm1/Desktop/vidrank/backend
python3 test_auth_flow.py
# Should show: ✅ User EXISTS in database!
```

---

## 🔍 Why This Happened

Firebase JWT tokens contain:
```json
{
  "aud": "your-firebase-project-id",  // ← This must match backend config
  "uid": "nBdObpDEybTNOIwAxWMxyGUsBDy2",
  "email": "business.fahadali@gmail.com",
  "iss": "https://securetoken.google.com/your-firebase-project-id"
}
```

Backend checks:
1. ✅ Token signature valid?
2. ✅ Not expired?
3. ❌ **Audience matches `AUTH_PROJECT_ID`?** ← Failed here!

---

## 📊 Before vs After

**BEFORE (Current):**
```
Extension sends: aud="your-real-project-id"
Backend expects: aud="vidrank" (default)
Result: 401 "wrong audience"
```

**AFTER (Fixed):**
```
Extension sends: aud="your-real-project-id"
Backend expects: aud="your-real-project-id" (from .dev.vars)
Result: ✅ 200 OK + session token
```

---

## 🚀 Next Steps

1. **Extract your Firebase Project ID** (use script or Firebase Console)
2. **Add to `.dev.vars`**
3. **Restart backend**
4. **Test login again**

---

## 💡 Quick Test Command

```bash
cd /Users/macm1/Desktop/vidrank/backend

# Get project ID from your token
echo "Paste your Firebase token from DevTools:"
python3 get_project_id.py

# Add to .dev.vars (replace YOUR_PROJECT_ID)
echo 'AUTH_PROJECT_ID="YOUR_PROJECT_ID"' > .dev.vars

# Restart backend
uv run python dev_server.py
```

---

## 📸 Send Me If Still Not Working

1. Output of `python3 get_project_id.py` (with your token)
2. Contents of `.dev.vars` file
3. Backend startup logs (first 20 lines)
4. New screenshot of Network request after fix

---

**The 401 is because backend doesn't know your Firebase project ID. Add it to `.dev.vars` and it will work!** ✅
