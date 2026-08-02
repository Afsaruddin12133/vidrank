// YouTube Auto Tag Generator - Background Service Worker

import { auth, db } from './firebase-config.js';
import { doc, getDoc, setDoc } from 'firebase/firestore';
import { GoogleAuthProvider, signInWithCredential, signOut, onAuthStateChanged } from 'firebase/auth/web-extension';

// Function to fetch and sync the dynamic API key from Firestore
async function syncApiKeyFromFirebase() {
  try {
    const docRef = doc(db, 'apikey', 'api');
    const docSnap = await getDoc(docRef);
    
    if (docSnap.exists()) {
      const fetchedKey = docSnap.data().key;
      if (fetchedKey) {
        chrome.storage.local.set({ groqApiKey: fetchedKey }, () => {
          console.log("[VidRank] Dynamic API key synced from Firebase.");
        });
      }
    } else {
      console.warn("[VidRank] No API key document found in Firestore!");
    }
  } catch (error) {
    console.error("[VidRank] Error fetching API key from Firebase:", error);
  }
}

// Sync key immediately whenever the Service Worker wakes up
syncApiKeyFromFirebase();

// System prompts
const TAG_SYSTEM_PROMPT = `You are an elite YouTube SEO Expert and Viral Growth Strategist. Your goal is to generate tags that maximize the algorithm's reach, increase Search Volume (CTR), and place the video in the 'Suggested' and 'Up Next' sections of YouTube.

INPUT ANALYSIS:
You will be provided with the Video Title and Video Description. Analyze them for:
1. Core Topic (The main subject).
2. Target Audience (Who is this for?).
3. Key Entities (People, Brands, Locations, or Tools mentioned).
4. Intent (Is it a tutorial, a vlog, a review, or news?).

STRICT TAG GENERATION RULES:
1. The 30/40/30 Distribution:
   - 30% Broad/Short Keywords (1 word): High-volume category tags.
   - 40% Specific/Medium Keywords (2-3 words): The "sweet spot" for search.
   - 30% Long-tail Keywords (4+ words): Specific user queries that face less competition.
2. Viral Injection: Include 2-3 high-trending tags relevant to the niche (e.g., 'viral', 'trending', '2026', 'tips').
3. Entity Mapping: If a specific name or brand is in the title/description, create 3 variations of that name as tags.
4. Searcher Intent: Write tags as if they are actual phrases a human would type into the YouTube search bar.
5. Negative Constraints: 
   - NO generic emotional fillers (e.g., 'beautiful day', 'amazing video').
   - NO hashtags (no # symbol).
   - NO numbering or bullet points.
   - NO conversational text or explanations.

OUTPUT FORMAT:
- Generate EXACTLY 20 tags.
- Format: Only a comma-separated list.
- Example: Tag 1, Tag 2, Tag 3... Tag 20.`;

const DESCRIPTION_SYSTEM_PROMPT = `You are a professional YouTube Copywriter and Conversion Optimizer. Your goal is to write a concise, punchy description that keeps viewers engaged, improves SEO, and encourages them to subscribe. Keep the output very short and compact.

SOP for Description Writing:
1. The Hook: 1-2 short sentences summarizing the video and including the main keyword.
2. Key Takeaways: A brief, 3-point bulleted list of what the viewer will learn or see.
3. Call to Action: A single sentence asking to Like and Subscribe.
4. The Hashtag Footer: End with 3 relevant hashtags.

TONE & STYLE:
- Keep sentences short.
- Very concise and to the point.
- Professional yet exciting.
- Do NOT write long paragraphs.

OUTPUT FORMAT:
- A very brief, ready-to-paste description.
- No labels like 'Hook:' or 'Summary:'—just write the actual content.`;

// Initialize default settings upon installation
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === chrome.runtime.OnInstalledReason.INSTALL) {
    const defaultSettings = {
      autoGenerate: false,
      autoInsert: true,
      autoSyncDescription: false, // Turned off by default so AI generation is controlled
      hashtagMode: false,
      maxTagsCount: 35,
      preferredSeparator: ",",
      debugMode: false,
      lastUpdated: new Date().toISOString()
    };

    chrome.storage.sync.set(defaultSettings, () => {
      if (chrome.runtime.lastError) {
        console.error("[YouTube Tag Generator] Error initializing sync settings:", chrome.runtime.lastError);
      } else {
        console.log("[YouTube Tag Generator] Default sync settings initialized.");
      }
    });

    // Sync dynamic Groq API Key from Firebase instead of using a hardcoded default
    syncApiKeyFromFirebase();
  }
});

// Listener for runtime messages
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "generateTags") {
    // 1. Check Usage limits first without incrementing
    syncUsageStats(false).then((stats) => {
      if (stats.plan === "free" && stats.usageCount >= 10) {
        return sendResponse({ success: false, error: "RATE_LIMIT_EXCEEDED" });
      }

      handleTagGeneration(request.title, request.description)
        .then(async tags => {
          // 2. Increment usage and await it before responding so content.js sees the fresh count
          await syncUsageStats(true).catch(console.error);
          sendResponse({ success: true, tags: tags });
        })
        .catch(err => sendResponse({ success: false, error: err.message }));
    }).catch(err => {
      sendResponse({ success: false, error: err.message });
    });
    return true; // Keep message channel open for async response
  } else if (request.action === "generateDescription") {
    handleDescriptionGeneration(request.title)
      .then(desc => sendResponse({ success: true, description: desc }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true; // Keep message channel open for async response
  } else if (request.action === "login") {
    handleGoogleLogin()
      .then(user => sendResponse({ success: true, user: user }))
      .catch(err => sendResponse({ success: false, error: err.message }));
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
  } else if (request.action === "syncUsage") {
    syncUsageStats(false)
      .then(stats => sendResponse({ success: true, stats }))
      .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
});

// Google Login Handler
async function handleGoogleLogin() {
  return new Promise((resolve, reject) => {
    chrome.identity.getAuthToken({ interactive: true }, async (token) => {
      if (chrome.runtime.lastError || !token) {
        return reject(new Error(chrome.runtime.lastError?.message || "Failed to get auth token."));
      }

      try {
        const credential = GoogleAuthProvider.credential(null, token);
        const userCredential = await signInWithCredential(auth, credential);
        const user = userCredential.user;

        // Check if user exists in Firestore
        const userRef = doc(db, "users", user.uid);
        const userDoc = await getDoc(userRef);

        if (!userDoc.exists()) {
          // Create new user profile matching the requested structure
          await setDoc(userRef, {
            email: user.email,
            isActive: true,
            name: user.displayName || "Unknown User",
            photoUrl: user.photoURL || "",
            plan: "free",
            uid: user.uid,
            usageCount: 0,
            lastUsageReset: Date.now()
          });
        }
        
        // Save auth state locally so content scripts know immediately
        chrome.storage.local.set({ isLoggedIn: true, uid: user.uid });
        
        // Sync limits
        await syncUsageStats(false);
        
        resolve({ uid: user.uid, email: user.email, name: user.displayName });
      } catch (error) {
        reject(error);
      }
    });
  });
}

// Sync Usage Stats Helper
async function syncUsageStats(increment = false) {
  // Service Workers drop auth.currentUser on wake. 
  // We must fetch the uid from local storage where we safely preserved it during login.
  const localData = await new Promise(resolve => chrome.storage.local.get(["uid"], resolve));
  const uid = localData.uid;

  if (!uid) {
    return { usageCount: 0, plan: "free" };
  }

  // CRITICAL FIX: Service Workers drop auth state. We must wait for Firebase to re-authenticate
  // before we make any Firestore requests, otherwise we get "Missing or insufficient permissions."
  if (!auth.currentUser) {
    await new Promise(resolve => {
      const unsubscribe = onAuthStateChanged(auth, user => {
        unsubscribe();
        resolve(user);
      });
    });
  }

  const userRef = doc(db, "users", uid);
  
  let userDoc;
  try {
    userDoc = await getDoc(userRef);
  } catch (err) {
    console.warn("Failed to get doc, using default", err);
  }
  
  if (!userDoc || !userDoc.exists()) {
    return { usageCount: 0, plan: "free" };
  }

  const data = userDoc.data();
  const now = Date.now();
  let usageCount = data.usageCount || 0;
  let lastUsageReset = data.lastUsageReset || 0;
  const plan = data.plan || "free";

  let needsUpdate = false;

  // Check if 24 hours have passed since last reset
  if (now - lastUsageReset > 86400000) {
    usageCount = 0;
    lastUsageReset = now;
    needsUpdate = true;
  }

  if (increment && plan === "free") {
    usageCount += 1;
    needsUpdate = true;
  }

  // Persist strictly back to Firestore if changed
  if (needsUpdate) {
    try {
      // Use setDoc with merge to ensure it writes robustly even if doc fields are missing
      await setDoc(userRef, { 
        usageCount: usageCount, 
        lastUsageReset: lastUsageReset 
      }, { merge: true });
    } catch (e) {
      console.error("[VidRank] Failed to sync usage to Firestore:", e);
    }
  }

  // Broadcast state locally for UI to read instantly
  await chrome.storage.local.set({ usageCount, plan });

  return { usageCount, plan };
}

// Groq API client helpers
async function fetchGroqApiKey() {
  return new Promise((resolve) => {
    chrome.storage.local.get({ groqApiKey: "" }, (data) => {
      resolve(data.groqApiKey ? data.groqApiKey.trim() : "");
    });
  });
}

async function callGroqAPI(systemPrompt, userContent) {
  const apiKey = await fetchGroqApiKey();
  if (!apiKey) {
    throw new Error("Missing Key: No Groq API Key found. Please add a valid key in the settings popup.");
  }

  try {
    const response = await fetch("https://api.groq.com/openai/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: "llama-3.3-70b-versatile",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: userContent }
        ],
        temperature: 0.7
      })
    });

    if (response.status === 401) {
      throw new Error("Invalid Key: The provided Groq API key is incorrect or unauthorized.");
    } else if (response.status === 429) {
      throw new Error("Rate Limits: Groq API rate limit exceeded. Please wait a moment before trying again.");
    } else if (!response.ok) {
      const errBody = await response.json().catch(() => ({}));
      const msg = errBody.error?.message || `HTTP status ${response.status}`;
      throw new Error(`Groq API Error: ${msg}`);
    }

    const data = await response.json();
    if (!data.choices || data.choices.length === 0 || !data.choices[0].message) {
      throw new Error("Failed to get a valid generation result from Groq API.");
    }

    return data.choices[0].message.content;
  } catch (error) {
    console.error("[YouTube Tag Generator] API Error:", error);
    throw error;
  }
}

async function handleTagGeneration(title, description) {
  const userContent = `Title: ${title || "Untitled"}\nDescription: ${description || "None"}`;
  const responseContent = await callGroqAPI(TAG_SYSTEM_PROMPT, userContent);

  // Clean tags output
  // Comma split and clean spaces
  const rawTags = responseContent.split(",")
    .map(t => t.replace(/[\r\n]+/g, " ").trim())
    .filter(t => t.length > 0);

  return rawTags;
}

async function handleDescriptionGeneration(title) {
  const userContent = `Title: ${title || "Untitled"}`;
  const responseContent = await callGroqAPI(DESCRIPTION_SYSTEM_PROMPT, userContent);
  return responseContent.trim();
}

console.log("[YouTube Tag Generator] Background service worker loaded.");
