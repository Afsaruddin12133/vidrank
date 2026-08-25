import { initializeApp, getApps, type FirebaseApp } from "firebase/app";
import {
  getAuth,
  signInWithPopup,
  GoogleAuthProvider,
  signOut as fbSignOut,
  onAuthStateChanged,
  type Auth,
  type User,
} from "firebase/auth";

export const firebaseConfig = {
  apiKey: "AIzaSyAlRH6242b-yDFn5E9yfyIwof6LsL7nWp8",
  authDomain: "vidrank-5e540.firebaseapp.com",
  projectId: "vidrank-5e540",
  storageBucket: "vidrank-5e540.firebasestorage.app",
  messagingSenderId: "5551217356",
  appId: "1:5551217356:web:528d9a9443cfb0a0e58069",
  measurementId: "G-LTP9PYKR6F",
};

export const BACKEND_URL = "https://vidrank-backend.fahad288ali.workers.dev/v1";

export async function getCurrentIdToken(): Promise<string> {
  const client = getClientAuth();
  if (client?.auth.currentUser) return client.auth.currentUser.getIdToken(true);
  throw new Error("Not signed in");
}

let app: FirebaseApp | null = null;
let auth: Auth | null = null;
let googleProvider: GoogleAuthProvider | null = null;

export function getClientAuth(): { auth: Auth; provider: GoogleAuthProvider } | null {
  if (typeof window === "undefined") return null;

  if (!app) {
    app = getApps().length === 0 ? initializeApp(firebaseConfig) : getApps()[0];
  }
  if (!auth) {
    auth = getAuth(app);
  }
  if (!googleProvider) {
    googleProvider = new GoogleAuthProvider();
    googleProvider.setCustomParameters({ prompt: "select_account" });
  }

  return { auth, provider: googleProvider };
}

export async function getFirebaseAuthToken(): Promise<string | null> {
  const client = getClientAuth();
  if (!client) return null;
  if (client.auth.currentUser) {
    return await client.auth.currentUser.getIdToken();
  }

  return new Promise((resolve) => {
    const unsubscribe = onAuthStateChanged(client.auth, async (user) => {
      unsubscribe();
      if (user) {
        try {
          resolve(await user.getIdToken());
        } catch {
          resolve(null);
        }
      } else {
        resolve(null);
      }
    });

    setTimeout(() => {
      unsubscribe();
      resolve(null);
    }, 4000);
  });
}


export interface VidRankUser {
  uid: string;
  email: string;
  name: string;
  photo_url: string;
  tier: "free" | "pro" | string;
  billing_price_id?: string | null;
  session_token?: string;
  quota?: {
    remaining: number;
    limit: number;
    resets_in_seconds?: number;
  };
}

const STORAGE_KEY = "vidrank_user_session";

export function getCachedUser(): VidRankUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setCachedUser(user: VidRankUser | null): void {
  if (typeof window === "undefined") return;
  try {
    if (user) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {}
}

export async function syncUserWithBackend(user: User): Promise<VidRankUser | null> {
  try {
    const idToken = await user.getIdToken(true);

    let res: Response;
    try {
      res = await fetch("/api/auth/login", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${idToken}`,
          "Content-Type": "application/json",
        },
      });
    } catch {
      res = await fetch(`${BACKEND_URL}/auth/login`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${idToken}`,
          "Content-Type": "application/json",
        },
      });
    }

    if (!res.ok) {
      console.warn("Backend auth sync responded with status:", res.status);
      const fallbackUser: VidRankUser = {
        uid: user.uid,
        email: user.email || "",
        name: user.displayName || user.email || "VidRank User",
        photo_url: user.photoURL || "",
        tier: "free",
        quota: { remaining: 10, limit: 10 },
      };
      setCachedUser(fallbackUser);
      return fallbackUser;
    }

    const data = await res.json();
    const syncedUser: VidRankUser = {
      uid: data.user?.uid || user.uid,
      email: data.user?.email || user.email || "",
      name: data.user?.name || user.displayName || user.email || "VidRank User",
      photo_url: data.user?.photo_url || user.photoURL || "",
      tier: data.user?.tier || "free",
      billing_price_id: data.user?.billing_price_id ?? null,
      session_token: data.session_token || "",
      quota: data.quota || { remaining: 10, limit: 10 },
    };

    setCachedUser(syncedUser);
    return syncedUser;
  } catch (err) {
    console.error("Failed to sync user with backend:", err);
    const fallbackUser: VidRankUser = {
      uid: user.uid,
      email: user.email || "",
      name: user.displayName || user.email || "VidRank User",
      photo_url: user.photoURL || "",
      tier: "free",
      quota: { remaining: 10, limit: 10 },
    };
    setCachedUser(fallbackUser);
    return fallbackUser;
  }
}

export async function loginWithGoogle(): Promise<VidRankUser> {
  const client = getClientAuth();
  if (!client) throw new Error("Firebase auth not available in SSR mode");

  const result = await signInWithPopup(client.auth, client.provider);
  const synced = await syncUserWithBackend(result.user);
  if (!synced) {
    throw new Error("Failed to authenticate session with VidRank backend");
  }

  // Dispatch global event for components to react
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent("vidrank:auth:change", { detail: { user: synced } })
    );
  }

  return synced;
}

export async function logout(): Promise<void> {
  const client = getClientAuth();
  if (client) {
    try {
      await fbSignOut(client.auth);
    } catch (e) {
      console.warn("Sign out error:", e);
    }
  }

  setCachedUser(null);

  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent("vidrank:auth:change", { detail: { user: null } })
    );
  }
}

export function initAuthListener(callback: (user: VidRankUser | null) => void): () => void {
  const client = getClientAuth();
  if (!client) return () => {};

  return onAuthStateChanged(client.auth, async (fbUser) => {
    if (fbUser) {
      const cached = getCachedUser();
      if (cached && cached.uid === fbUser.uid) {
        callback(cached);
      }
      const synced = await syncUserWithBackend(fbUser);
      callback(synced);
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("vidrank:auth:change", { detail: { user: synced } })
        );
      }
    } else {
      setCachedUser(null);
      callback(null);
      if (typeof window !== "undefined") {
        window.dispatchEvent(
          new CustomEvent("vidrank:auth:change", { detail: { user: null } })
        );
      }
    }
  });
}
