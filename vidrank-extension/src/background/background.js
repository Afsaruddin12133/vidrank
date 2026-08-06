// VidRank — Background Service Worker (thin auth+fetch shim)
// All AI generation, quota, and retry-throttling live behind the backend.
// The extension holds NO provider key; it only sends a Firebase ID token.

import { auth } from './firebase-config.js';
import { GoogleAuthProvider, signInWithCredential, signOut } from 'firebase/auth/web-extension';

// Backend base URL - Environment-based configuration
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL
  || 'http://localhost:8787/v1';

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

    // Save ONLY non-sensitive quota metrics (NO tokens stored in storage)
    if (data.user) {
      await chrome.storage.local.set({
        plan: data.user?.tier || "free",
        usageLimit: data.quota?.limit || 10,
        quotaRemaining: data.quota?.remaining || 0
      });
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
      console.error('[VidRank] Failed to parse response');
      return { success: false, error: "INVALID_RESPONSE" };
    }

    if (res.status === 200 && body.success) {
      persistUsage(body.usage, body.retry_after);
      return {
        success: true,
        tags: body.tags || [],
        description: body.description || "",
        usage: body.usage,
        retry_after: body.retry_after || 0
      };
    }

    const error = body.error || `HTTP ${res.status}`;
    persistUsage(body.usage, body.retry_after);
    
    return {
      success: false,
      error,
      retry_after: body.retry_after || 0,
      usage: body.usage
    };
  } catch (err) {
    console.error("[VidRank] Backend error:", err);
    return { 
      success: false, 
      error: err.message || "Network error"
    };
  }
}

// Refresh usage stats from backend
async function refreshUsage() {
  let token;
  try { 
    token = await getIdToken(); 
  } catch (_) {
    return { usageCount: 0, plan: "free", usageLimit: 10, retry_after: 0 };
  }

  try {
    const res = await fetch(`${BACKEND_URL}/me`, {
      headers: { "Authorization": `Bearer ${token}` }
    });

    if (!res.ok) {
      console.error("[VidRank] /me endpoint failed:", res.status);
      return { usageCount: 0, plan: "free", usageLimit: 10, retry_after: 0 };
    }

    const body = await res.json();
    const stats = {
      usageCount: body.usageCount || 0,
      plan: body.plan || "free",
      usageLimit: body.usageLimit || 10,
      retry_after: body.retry_after || 0
    };

    await chrome.storage.local.set(stats);
    return stats;
  } catch (err) {
    console.error("[VidRank] /me network error:", err);
    return { usageCount: 0, plan: "free", usageLimit: 10, retry_after: 0 };
  }
}

// Store usage locally
function persistUsage(usage, retry_after) {
  if (usage) {
    chrome.storage.local.set({
      usageCount: usage.usageCount || 0,
      usageLimit: usage.usageLimit || 10,
      retry_after: retry_after || 0
    });
  }
}

console.log('[VidRank] Background script ready');
