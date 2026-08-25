// VidRank — Background Service Worker (thin auth+fetch shim)
// All AI generation, quota, and retry-throttling live behind the backend.
// The extension holds NO provider key; it only sends a Firebase ID token.

import { auth } from './firebase-config.js';
import { GoogleAuthProvider, signInWithCredential, signOut } from 'firebase/auth/web-extension';

// Backend base URL - Environment-based configuration
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL
  || 'https://vidrank-backend.fahad288ali.workers.dev/v1';

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

    chrome.storage.sync.set(defaultSettings, () => {});
  }
});

// Listener for runtime messages
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
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
    handleGoogleLogin()
      .then(user => {
        sendResponse({ success: true, user });
      })
      .catch(err => {
        sendResponse({ success: false, error: err.message });
      });
    return true;


  } else if (request.action === "logout") {
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
    refreshUsage()
      .then(stats => {
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
    // best-effort: quota refresh failure must not break login
  }

  return user;
}

// Send login request event to backend (/v1/auth/login) to register/sync user session & quotas
async function syncLoginWithBackend(user) {
  try {
    const idToken = await user.getIdToken(true);

    const res = await fetch(`${BACKEND_URL}/auth/login`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${idToken}`,
        "Content-Type": "application/json"
      }
    });

    if (!res.ok) {
      return null;
    }

    const data = await res.json();

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
    return null;
  }
}

// Directly extract Firebase auth session data from IndexedDB ("firebaseLocalStorageDb" -> "firebaseLocalStorage")
async function getAuthDataFromIndexedDB() {
  return new Promise((resolve) => {
    try {
      const request = indexedDB.open('firebaseLocalStorageDb');
      request.onerror = () => {
        resolve(null);
      };
      request.onsuccess = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains('firebaseLocalStorage')) {
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
            resolve(sts);
          } else {
            resolve(null);
          }
        };
        getAllReq.onerror = () => {
          db.close();
          resolve(null);
        };
      };
    } catch (e) {
      resolve(null);
    }
  });
}

// Write refreshed sts tokens back to IndexedDB (firebaseLocalStorageDb).
// securetoken rotates the refresh_token on every exchange; without this
// write-back the DB keeps the stale (soon-invalidated) pair forever.
async function saveStsToIndexedDB(sts) {
  return new Promise((resolve) => {
    try {
      const request = indexedDB.open('firebaseLocalStorageDb');
      request.onerror = () => resolve(false);
      request.onsuccess = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains('firebaseLocalStorage')) {
          db.close();
          return resolve(false);
        }
        const tx = db.transaction('firebaseLocalStorage', 'readwrite');
        const store = tx.objectStore('firebaseLocalStorage');
        const getAllReq = store.getAll();
        getAllReq.onsuccess = () => {
          const entries = getAllReq.result || [];
          const entry = entries.find(e => e.fbase_key && e.fbase_key.includes('[DEFAULT]')) || entries[0];
          if (!entry) {
            db.close();
            return resolve(false);
          }
          entry.value.stsTokenManager = sts;
          store.put(entry);
          tx.oncomplete = () => { db.close(); resolve(true); };
          tx.onerror = () => { db.close(); resolve(false); };
        };
        getAllReq.onerror = () => { db.close(); resolve(false); };
      };
    } catch (e) {
      resolve(false);
    }
  });
}

// Silent recovery for a dead (rotated) refresh token: mint a brand-new
// Firebase session from Chrome's own OAuth grant — no user interaction.
// Requires only that the user hasn't revoked the extension's Google permission.
async function silentReauth() {
  try {
    const { token } = await chrome.identity.getAuthToken({ interactive: false });
    if (!token) return null;
    try {
      const credential = GoogleAuthProvider.credential(null, token);
      const userCredential = await signInWithCredential(auth, credential);
      return userCredential.user;
    } catch (err) {
      // Stale cached Chrome OAuth token — drop it and mint a fresh one once.
      await new Promise(r => chrome.identity.removeCachedAuthToken({ token }, r));
      const retry = await chrome.identity.getAuthToken({ interactive: false });
      if (!retry) return null;
      const credential = GoogleAuthProvider.credential(null, retry.token);
      const userCredential = await signInWithCredential(auth, credential);
      return userCredential.user;
    }
  } catch (err) {
    return null;
  }
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
      return accessToken;
    }

    // If expired, exchange refreshToken for a new accessToken via Google OAuth API
    if (refreshToken) {
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
            await saveStsToIndexedDB({
              accessToken: refreshData.id_token,
              refreshToken: refreshData.refresh_token || refreshToken,
              expirationTime: Date.now() + (refreshData.expires_in || 3600) * 1000
            });
            return refreshData.id_token;
          }
        }
      } catch (err) {
        // best-effort token refresh
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
    const reauthed = await silentReauth();
    if (reauthed) {
      return reauthed.getIdToken(true);
    }
    // Session unrecoverable — flip storage so every UI surface (popup,
    // sidepanel, YouTube sidebar) switches to its logged-out view.
    chrome.storage.local.set({ isLoggedIn: false });
    throw new Error("NOT_LOGGED_IN");
  }

  return user.getIdToken(true);
}

// Auth/token failures must read as an action, not a code — users hit these
// after the Firebase refresh-token rotation issue and need to re-login.
function friendlyError(err) {
  const raw = String((err && (err.message || err.error)) || err || '');
  const key = raw.toUpperCase();
  const needsRelogin =
    key.includes('NOT_LOGGED_IN') ||
    key.includes('UNAUTHORIZED') ||
    key.includes('TOKEN') ||
    key.includes('AUTH') ||
    key.includes('401');
  if (needsRelogin) {
    return 'Your session has expired. Please open the VidRank extension popup, log out, then log in again.';
  }
  return raw || 'Something went wrong. Please try again.';
}

// Call backend to generate tags
async function callBackendGenerate(title, description) {
  // OPTIMISTIC UPDATE: Increment locally immediately for instant UI feedback
  const originalCache = { ...quotaCache };
  if (quotaCache.usageLimit >= 0 && quotaCache.plan === 'free') {
    quotaCache = {
      ...quotaCache,
      usageCount: quotaCache.usageCount + 1,
      remaining: Math.max(0, quotaCache.remaining - 1)
    };
    broadcastQuotaUpdate(quotaCache);
  }
  
  try {
    const token = await getIdToken();

    const res = await fetch(`${BACKEND_URL}/generate`, {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ title: title || "", description: description || "" })
    });

    let body = {};
    try {
      body = await res.json();
    } catch (e) {
      // Keep optimistic update on parse error
      return { success: false, error: "INVALID_RESPONSE" };
    }

    if (res.status === 200 && body.success) {
      // SYNC WITH SERVER: If backend has actual count, use it; otherwise keep optimistic
      if (body.usage && typeof body.usage.used === 'number' && body.usage.used > 0) {
        persistUsage(body.usage, body.retry_after);
      } else {
        // Backend didn't increment (DO issue), but we already did optimistically
        broadcastQuotaUpdate(quotaCache);
      }

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

    const error = friendlyError(body.error || `HTTP ${res.status}`);

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
    // REVERT: On network error, restore original quota
    quotaCache = originalCache;
    broadcastQuotaUpdate(quotaCache);
    return {
      success: false,
      error: friendlyError(err)
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
  if (!usage) return;
  
  const limit = (typeof usage.limit === 'number' && usage.limit >= 0) ? usage.limit : -1;
  const used = usage.used || 0;
  
  quotaCache = {
    usageCount: used,
    remaining: limit >= 0 ? Math.max(0, limit - used) : limit,
    usageLimit: limit,
    plan: usage.plan || 'free',
    retry_after: retry_after || 0
  };
  broadcastQuotaUpdate(quotaCache);
}

let quotaCache = { plan: 'free', usageCount: 0, usageLimit: 10, retry_after: 0 };
