// VidRank — Background Service Worker (thin auth+fetch shim)
// All AI generation, quota, and retry-throttling live behind the backend.
// The extension holds NO provider key; it only sends a Firebase ID token.

import { auth } from './firebase-config.js';
import { GoogleAuthProvider, signInWithCredential, signOut } from 'firebase/auth/web-extension';

// Backend base URL - Environment-based configuration
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL
  || 'https://vidrank-backend.fahad288ali.workers.dev/v1';

console.log('[VidRank] Background script loaded. Backend URL:', BACKEND_URL);

// Initialize default settings upon installation
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === chrome.runtime.OnInstalledReason.INSTALL) {
    const defaultSettings = {
      autoGenerate: false,
      autoInsert: true,
      autoSyncDescription: false,
      hashtagMode: false,
      maxTagsCount: 35,
      preferredSeparator: ",",
      debugMode: false,
      lastUpdated: new Date().toISOString()
    };

    chrome.storage.sync.set(defaultSettings, () => {
      if (chrome.runtime.lastError) {
        console.error("[VidRank] Error initializing sync settings:", chrome.runtime.lastError);
      } else {
        console.log("[VidRank] Default sync settings initialized.");
      }
    });
  }
});

// Listener for runtime messages
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('[VidRank] Received message:', request.action);

  if (request.action === "generateTags") {
    callBackendGenerate(request.title, request.description)
      .then(res => sendResponse(res))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;

  } else if (request.action === "generateDescription") {
    callBackendGenerate(request.title, "")
      .then(res => sendResponse(res))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;

  } else if (request.action === "login") {
    // Native Chrome OAuth (chrome.identity) + Firebase credential exchange.
    // signInWithPopup is blocked by MV3 CSP, so no offscreen document is needed.
    console.log('[VidRank] login action received');
    handleGoogleLogin()
      .then(user => {
        console.log('[VidRank] Firebase login successful:', user.email);
        sendResponse({ success: true, user });
      })
      .catch(err => {
        console.error('[VidRank] Firebase login failed:', err);
        sendResponse({ success: false, error: err.message });
      });
    return true;


  } else if (request.action === "logout") {
    console.log('[VidRank] Logout action triggered');
    signOut(auth)
      .then(() => {
        chrome.storage.local.set({ isLoggedIn: false });
        sendResponse({ success: true });
      })
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;

  } else if (request.action === "getAuthState") {
    chrome.storage.local.get({ isLoggedIn: false }, (data) => {
      sendResponse({ isLoggedIn: data.isLoggedIn });
    });
    return true;

  } else if (request.action === "getQuota") {
    console.log('📊 [QUOTA] Popup requested quota, refreshing from backend...');
    refreshUsage()
      .then(stats => {
        console.log('📊 [QUOTA] Sending to popup:', stats);
        sendResponse({ success: true, stats });
      })
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;

  } else if (request.action === "getStats") {
    sendResponse({ success: true, stats: quotaCache });
    return true;

  } else if (request.action === "syncUsage") {
    refreshUsage()
      .then(stats => sendResponse({ success: true, stats }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
});

// Google Login Handler — native Chrome OAuth + Firebase credential exchange.
// Official MV3 method: signInWithPopup needs to inject https://apis.google.com
// scripts, which MV3 extension pages block (CSP script-src 'self').
async function handleGoogleLogin() {
  console.log('[VidRank] Starting Google login via chrome.identity...');

  const { token } = await chrome.identity.getAuthToken({ interactive: true });
  const credential = GoogleAuthProvider.credential(null, token);
  const userCredential = await signInWithCredential(auth, credential);
  const user = userCredential.user;

  // Save auth state locally
  await chrome.storage.local.set({
    isLoggedIn: true,
    uid: user.uid,
    email: user.email,
    displayName: user.displayName || '',
    photoURL: user.photoURL || ''
  });

  // Notify backend of login event (/v1/auth/login)
  await syncLoginWithBackend(user);

  try { await refreshUsage(); } catch (e) {
    console.warn('[VidRank] Could not sync usage:', e);
  }

  return user;
}

// Send login request event to backend (/v1/auth/login) to register/sync user session & quotas
async function syncLoginWithBackend(user) {
  try {
    const idToken = await user.getIdToken(true);
    console.log('[VidRank] Sending login sync request to backend:', `${BACKEND_URL}/auth/login`);

    const res = await fetch(`${BACKEND_URL}/auth/login`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${idToken}`,
        "Content-Type": "application/json"
      }
    });

    if (!res.ok) {
      console.error("[VidRank] Backend /v1/auth/login failed with status:", res.status);
      return null;
    }

    const data = await res.json();
    console.log("[VidRank] Backend /v1/auth/login response:", data);

    // Keep quota in sync
    if (data.user) {
      const limit = (data.quota && typeof data.quota.limit === 'number' && data.quota.limit >= 0)
        ? data.quota.limit : -1;  // -1 = unlimited (pro)
      const remaining = (data.quota && typeof data.quota.remaining === 'number' && data.quota.remaining >= 0)
        ? data.quota.remaining : (limit >= 0 ? limit : -1);
      const used = limit >= 0 && remaining >= 0 ? Math.max(0, limit - remaining) : 0;
      quotaCache = {
        plan: data.user?.tier || "free",
        usageLimit: limit,
        usageCount: used,
        quotaRemaining: remaining,
        remaining: remaining
      };
      broadcastQuotaUpdate(quotaCache);
    }

    return data;
  } catch (err) {
    console.error("[VidRank] Failed to send login request to backend:", err);
    return null;
  }
}

// Directly extract Firebase auth session data from IndexedDB ("firebaseLocalStorageDb" -> "firebaseLocalStorage")
async function getAuthDataFromIndexedDB() {
  return new Promise((resolve) => {
    try {
      const request = indexedDB.open('firebaseLocalStorageDb');
      request.onerror = (err) => {
        console.error('[VidRank IndexedDB] Failed to open firebaseLocalStorageDb:', err);
        resolve(null);
      };
      request.onsuccess = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains('firebaseLocalStorage')) {
          console.warn('[VidRank IndexedDB] Store firebaseLocalStorage not found');
          db.close();
          return resolve(null);
        }
        const tx = db.transaction('firebaseLocalStorage', 'readonly');
        const store = tx.objectStore('firebaseLocalStorage');
        const getAllReq = store.getAll();
        getAllReq.onsuccess = () => {
          const entries = getAllReq.result || [];
          const defaultEntry = entries.find(e => e.fbase_key && e.fbase_key.includes('[DEFAULT]')) || entries[0];
          db.close();
          if (defaultEntry && defaultEntry.value && defaultEntry.value.stsTokenManager) {
            const sts = defaultEntry.value.stsTokenManager;
            console.log('[VidRank IndexedDB] Found Auth Entry in IndexedDB!');
            resolve(sts);
          } else {
            console.warn('[VidRank IndexedDB] No auth tokens found in IndexedDB entries:', entries);
            resolve(null);
          }
        };
        getAllReq.onerror = (err) => {
          console.error('[VidRank IndexedDB] Failed to read store entries:', err);
          db.close();
          resolve(null);
        };
      };
    } catch (e) {
      console.error('[VidRank IndexedDB] Exception during IndexedDB read:', e);
      resolve(null);
    }
  });
}

// Get Firebase ID token directly from memory, or fallback to IndexedDB
async function getIdToken() {
  // 1. Check active Firebase Auth memory instance
  if (auth.currentUser) {
    const memToken = await auth.currentUser.getIdToken(true);
    return memToken;
  }

  // 2. Read auth tokens directly from IndexedDB (firebaseLocalStorageDb)
  const stsTokenManager = await getAuthDataFromIndexedDB();
  if (stsTokenManager) {
    const { accessToken, refreshToken, expirationTime } = stsTokenManager;
    const now = Date.now();

    // If access token is active (with 60s safety window)
    if (accessToken && expirationTime && (expirationTime - now > 60000)) {
      console.log('[VidRank Auth] Using active Access Token from IndexedDB');
      return accessToken;
    }

    // If expired, exchange refreshToken for a new accessToken via Google OAuth API
    if (refreshToken) {
      console.log('[VidRank Auth] Refreshing expired Access Token using Refresh Token...');
      try {
        const apiKey = "AIzaSyAlRH6242b-yDFn5E9yfyIwof6LsL7nWp8";
        const refreshRes = await fetch(`https://securetoken.googleapis.com/v1/token?key=${apiKey}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            grant_type: 'refresh_token',
            refresh_token: refreshToken
          })
        });

        if (refreshRes.ok) {
          const refreshData = await refreshRes.json();
          if (refreshData.id_token) {
            console.log('[VidRank Auth] Successfully acquired fresh ID Token');
            return refreshData.id_token;
          }
        }
      } catch (err) {
        console.warn('[VidRank Auth] Failed to refresh token from IndexedDB refreshToken:', err);
      }
    }
  }

  // 3. Fallback: Wait for onAuthStateChanged listener
  const user = await new Promise(resolve => {
    const unsub = auth.onAuthStateChanged(u => {
      if (u) {
        unsub();
        resolve(u);
      }
    });
    setTimeout(() => {
      unsub();
      resolve(null);
    }, 4000);
  });

  if (!user) {
    throw new Error("NOT_LOGGED_IN");
  }

  return user.getIdToken(true);
}

// Call backend to generate tags
async function callBackendGenerate(title, description) {
  console.log('🔵 [QUOTA] BEFORE API CALL:', {
    used: quotaCache.usageCount,
    remaining: quotaCache.remaining,
    limit: quotaCache.usageLimit,
    plan: quotaCache.plan
  });
  
  // OPTIMISTIC UPDATE: Increment locally immediately for instant UI feedback
  const originalCache = { ...quotaCache };
  if (quotaCache.usageLimit >= 0 && quotaCache.plan === 'free') {
    quotaCache = {
      ...quotaCache,
      usageCount: quotaCache.usageCount + 1,
      remaining: Math.max(0, quotaCache.remaining - 1)
    };
    console.log('⚡ [QUOTA] OPTIMISTIC INCREMENT:', {
      from: { used: originalCache.usageCount, remaining: originalCache.remaining },
      to: { used: quotaCache.usageCount, remaining: quotaCache.remaining }
    });
    broadcastQuotaUpdate(quotaCache);
  }
  
  console.log('📤 [REQUEST] Sending to backend:', {
    url: `${BACKEND_URL}/generate`,
    title: title.substring(0, 50) + '...',
    descriptionLength: description.length
  });
  
  try {
    const token = await getIdToken();
    console.log('🔑 [AUTH] Got ID token, length:', token.length);

    const res = await fetch(`${BACKEND_URL}/generate`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ title: title || "", description: description || "" })
    });

    console.log('📬 [RESPONSE] Status:', res.status, 'OK:', res.ok);

    let body = {};
    try {
      body = await res.json();
      console.log('📬 [RESPONSE] Full body:', JSON.stringify(body, null, 2));
    } catch (e) {
      console.error('[VidRank] Failed to parse response');
      // Keep optimistic update on parse error
      return { success: false, error: "INVALID_RESPONSE" };
    }

    if (res.status === 200 && body.success) {
      console.log('📥 [QUOTA] SERVER RESPONSE:', body.usage);
      
      // SYNC WITH SERVER: If backend has actual count, use it; otherwise keep optimistic
      if (body.usage && typeof body.usage.used === 'number' && body.usage.used > 0) {
        console.log('✅ [QUOTA] Backend confirmed usage, syncing...');
        persistUsage(body.usage, body.retry_after);
      } else {
        console.log('⚠️ [QUOTA] Backend returned used=0, keeping optimistic update');
        // Backend didn't increment (DO issue), but we already did optimistically
        broadcastQuotaUpdate(quotaCache);
      }
      
      console.log('🟢 [QUOTA] AFTER UPDATE:', {
        used: quotaCache.usageCount,
        remaining: quotaCache.remaining,
        limit: quotaCache.usageLimit,
        plan: quotaCache.plan
      });
      
      return {
        success: true,
        tags: body.tags || [],
        description: body.description || "",
        usage: {
          used: quotaCache.usageCount,  // Return our optimistic count
          limit: quotaCache.usageLimit,
          plan: quotaCache.plan
        },
        retry_after: body.retry_after || 0
      };
    }

    const error = body.error || `HTTP ${res.status}`;
    console.log('🔴 [QUOTA] ERROR:', error, 'Reverting optimistic update');
    
    // REVERT: On error, restore original quota
    quotaCache = originalCache;
    broadcastQuotaUpdate(quotaCache);
    
    return {
      success: false,
      error,
      retry_after: body.retry_after || 0,
      usage: body.usage
    };
  } catch (err) {
    console.error("🔴 [QUOTA] Backend error:", err, 'Reverting optimistic update');
    // REVERT: On network error, restore original quota
    quotaCache = originalCache;
    broadcastQuotaUpdate(quotaCache);
    return {
      success: false,
      error: err.message || "Network error"
    };
  }
}

// Refresh usage stats from backend
let lastQuotaFetch = 0;

async function refreshUsage(force = false) {
  const now = Date.now();
  if (!force && quotaCache && quotaCache.usageLimit !== undefined && (now - lastQuotaFetch < 1500)) {
    return quotaCache;
  }

  let token;
  try {
    token = await getIdToken();
  } catch (_) {
    return { usageCount: 0, remaining: 10, plan: "free", usageLimit: 10, retry_after: 0 };
  }

  try {
    const res = await fetch(`${BACKEND_URL}/me`, {
      headers: { "Authorization": `Bearer ${token}` }
    });

    if (!res.ok) {
      console.error("[VidRank] /me endpoint failed:", res.status);
      return { usageCount: 0, remaining: 10, plan: "free", usageLimit: 10, retry_after: 0 };
    }

    const body = await res.json();
    const rawLimit = body.quota_limit;
    const limit = (typeof rawLimit === 'number')
      ? (rawLimit >= 0 ? rawLimit : -1)
      : 10;
    const remaining = typeof body.quota_remaining === 'number' && body.quota_remaining >= 0
      ? body.quota_remaining
      : limit;
    const stats = {
      usageCount: limit >= 0 && remaining >= 0 ? Math.max(0, limit - remaining) : 0,
      remaining: (body.is_suspended || body.is_active === 0) ? 0 : remaining,
      plan: body.tier || "free",
      is_active: body.is_active !== undefined ? body.is_active : 1,
      is_suspended: Boolean(body.is_suspended || body.is_active === 0),
      usageLimit: limit,
      retry_after: 0,
      resets_in_seconds: body.resets_in_seconds || 0
    };

    lastQuotaFetch = Date.now();
    quotaCache = stats;
    broadcastQuotaUpdate(stats);
    return stats;
  } catch (err) {
    console.error("[VidRank] /me network error:", err);
    return { usageCount: 0, remaining: 10, plan: "free", usageLimit: 10, retry_after: 0 };
  }
}

function broadcastQuotaUpdate(stats) {
  if (!stats) return;
  try {
    chrome.storage.local.set({ quotaStats: stats });
    chrome.runtime.sendMessage({ action: 'quotaUpdated', stats }).catch(() => {});
  } catch (e) {}
}

// Keep latest usage in memory (never persisted to chrome.storage.local)
function persistUsage(usage, retry_after) {
  if (!usage) {
    console.log('⚠️ [QUOTA] persistUsage called with no usage data');
    return;
  }
  
  const limit = (typeof usage.limit === 'number' && usage.limit >= 0) ? usage.limit : -1;
  const used = usage.used || 0;
  
  const oldCache = { ...quotaCache };
  
  quotaCache = {
    usageCount: used,
    remaining: limit >= 0 ? Math.max(0, limit - used) : limit,
    usageLimit: limit,
    plan: usage.plan || 'free',
    retry_after: retry_after || 0
  };
  
  console.log('💾 [QUOTA] persistUsage UPDATE:', {
    from: { used: oldCache.usageCount, remaining: oldCache.remaining },
    to: { used: quotaCache.usageCount, remaining: quotaCache.remaining },
    serverData: usage
  });
  broadcastQuotaUpdate(quotaCache);
}

let quotaCache = { plan: 'free', usageCount: 0, usageLimit: 10, retry_after: 0 };

console.log('[VidRank] Background script ready');
