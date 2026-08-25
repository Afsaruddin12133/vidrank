/**
 * Paddle Billing Client Integration (Paddle.js v2)
 *
 * Configured for Live Environment by default.
 * Handles overlay checkout, Retain (pwCustomer), and event callbacks.
 */

declare global {
  interface Window {
    Paddle?: any;
  }
}

export const PADDLE_CLIENT_TOKEN =
  import.meta.env.PUBLIC_PADDLE_CLIENT_TOKEN || "live_5a7c54fd74fed7924d907376051";

export const PRICE_ID_PRO_MONTHLY =
  import.meta.env.PUBLIC_PADDLE_PRO_PRICE_ID_MONTHLY || "pri_01m0tb2e9n3naxfgp8d2c9f9at";

export const PRICE_ID_PRO_YEARLY =
  import.meta.env.PUBLIC_PADDLE_PRO_PRICE_ID_YEARLY || "pri_01m0tb2emy5wy8gbk7y8pmdpnw";


let paddleInitialized = false;

/**
 * Load Paddle.js CDN script dynamically
 */
export async function loadPaddleScript(): Promise<void> {
  if (typeof window === "undefined") return;
  if (window.Paddle) return;

  return new Promise((resolve, reject) => {
    const existing = document.getElementById("paddle-js-sdk");
    if (existing) {
      existing.addEventListener("load", () => resolve());
      existing.addEventListener("error", (e) => reject(e));
      return;
    }

    const script = document.createElement("script");
    script.id = "paddle-js-sdk";
    script.src = "https://cdn.paddle.com/paddle/v2/paddle.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = (e) => reject(new Error("Failed to load Paddle SDK: " + e));
    document.head.appendChild(script);
  });
}

/**
 * Initialize Paddle SDK in Live mode with optional Retain (pwCustomer)
 */
export async function initPaddle(customerPaddleId?: string): Promise<boolean> {
  if (typeof window === "undefined") return false;

  await loadPaddleScript();

  if (!window.Paddle) {
    console.warn("Paddle SDK not available on window");
    return false;
  }

  if (!paddleInitialized) {
    try {
      // NOTE: In Paddle.js v2, Live is the default. Do NOT set sandbox.
      window.Paddle.Initialize({
        token: PADDLE_CLIENT_TOKEN,
        pwCustomer: customerPaddleId ? { id: customerPaddleId } : undefined,
        eventCallback: (data: any) => {
          if (data && (data.name === "checkout.completed" || data.name === "checkout.payment.successful")) {
            console.log("[Paddle] Checkout completed successfully:", data);
            // Notify application
            window.dispatchEvent(new CustomEvent("vidrank:checkout:success", { detail: data }));
            // Reload or refresh session
            setTimeout(() => {
              window.location.href = "/?upgraded=true#pricing";
            }, 1500);
          }
        },
      });
      paddleInitialized = true;
    } catch (err) {
      console.error("Error initializing Paddle:", err);
      return false;
    }
  }

  return true;
}

export interface CheckoutOptions {
  priceId: string;
  userEmail: string;
  firebaseUid: string;
  customerPaddleId?: string;
}

/**
 * Open Paddle Live Checkout overlay
 */
export async function openPaddleCheckout(opts: CheckoutOptions): Promise<void> {
  await initPaddle(opts.customerPaddleId);

  if (!window.Paddle) {
    throw new Error("Paddle SDK could not be loaded");
  }

  window.Paddle.Checkout.open({
    items: [
      {
        priceId: opts.priceId,
        quantity: 1,
      },
    ],
    customer: opts.userEmail ? { email: opts.userEmail } : undefined,
    customData: {
      firebase_uid: opts.firebaseUid,
      email: opts.userEmail,
      source: "vidrank_landing",
    },
    settings: {
      displayMode: "overlay",
      theme: "dark",
      locale: "en",
      successUrl: `${window.location.origin}/?upgraded=true#pricing`,
    },
  });
}
