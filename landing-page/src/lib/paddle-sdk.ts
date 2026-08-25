/**
 * Paddle Billing — Client SDK helper (supports sandbox + live)
 *
 * Environment is read from PUBLIC_PADDLE_ENVIRONMENT ("sandbox" | "live").
 * Token is read from PUBLIC_PADDLE_CLIENT_TOKEN.
 * Both are required — missing either throws loudly so you never accidentally
 * run against the wrong Paddle account.
 */

declare global {
  interface Window {
    Paddle?: any;
  }
}

// ─── Fail loudly if env vars are missing ─────────────────────────────────────

function requireEnv(key: string): string {
  const val = (import.meta.env as any)[key];
  if (!val) {
    throw new Error(
      `[Paddle] Missing required env var "${key}". ` +
        `Set it in .env and restart the dev server.`
    );
  }
  return val as string;
}

export const PADDLE_ENV: "sandbox" | "live" = (() => {
  const env = requireEnv("PUBLIC_PADDLE_ENVIRONMENT");
  if (env !== "sandbox" && env !== "live") {
    throw new Error(
      `[Paddle] PUBLIC_PADDLE_ENVIRONMENT must be "sandbox" or "live", got "${env}"`
    );
  }
  return env as "sandbox" | "live";
})();

export const PADDLE_CLIENT_TOKEN = requireEnv("PUBLIC_PADDLE_CLIENT_TOKEN");

// ─── SDK loader ───────────────────────────────────────────────────────────────

let sdkLoaded = false;
let initDone = false;

export async function loadPaddleScript(): Promise<void> {
  if (typeof window === "undefined") return;
  if (sdkLoaded && window.Paddle) return;

  await new Promise<void>((resolve, reject) => {
    if (document.getElementById("paddle-js-sdk")) {
      resolve();
      return;
    }
    const s = document.createElement("script");
    s.id = "paddle-js-sdk";
    s.src = "https://cdn.paddle.com/paddle/v2/paddle.js";
    s.async = true;
    s.onload = () => {
      sdkLoaded = true;
      resolve();
    };
    s.onerror = () => reject(new Error("[Paddle] Failed to load paddle.js"));
    document.head.appendChild(s);
  });
}

// ─── Initialise (idempotent) ──────────────────────────────────────────────────

export async function initPaddle(customerEmail?: string): Promise<boolean> {
  if (typeof window === "undefined") return false;

  await loadPaddleScript();

  if (!window.Paddle) {
    console.error("[Paddle] SDK not on window after load");
    return false;
  }

  if (!initDone) {
    if (PADDLE_ENV === "sandbox") {
      window.Paddle.Environment.set("sandbox");
    }
    // For live, no call needed — live is default in Paddle.js v2

    window.Paddle.Initialize({
      token: PADDLE_CLIENT_TOKEN,
      eventCallback(data: any) {
        const { name } = data ?? {};
        if (
          name === "checkout.completed" ||
          name === "checkout.payment.successful"
        ) {
          console.log("[Paddle] checkout.completed", data);
          window.dispatchEvent(
            new CustomEvent("vidrank:checkout:success", { detail: data })
          );
          setTimeout(() => {
            window.location.href = "/welcome";
          }, 1500);
        }
      },
    });

    initDone = true;
  }

  return true;
}

// ─── PricePreview ─────────────────────────────────────────────────────────────

export interface PaddleFormattedPrice {
  subtotal: string;
  total: string;
  discount: string;
  tax: string;
}

export interface PaddlePriceResult {
  priceId: string;
  formattedTotals: PaddleFormattedPrice;
  currencyCode: string;
}

/**
 * Fetch localised prices for one or more price IDs.
 *
 * Pass `countryCode` only when you have a real ISO-3166-1 alpha-2 code from
 * a trusted server-side header. If absent, Paddle auto-detects from IP.
 * Never pass an internal sentinel like "OTHERS" to Paddle.
 */
export async function fetchPrices(
  priceIds: string[],
  countryCode?: string
): Promise<Map<string, PaddlePriceResult>> {
  await initPaddle();

  if (!window.Paddle) throw new Error("[Paddle] SDK not initialised");

  const request: Record<string, any> = {
    items: priceIds.map((id) => ({ priceId: id, quantity: 1 })),
  };
  if (countryCode) {
    request.address = { countryCode };
  }

  const response = await window.Paddle.PricePreview(request);
  const result = new Map<string, PaddlePriceResult>();

  for (const item of response?.data?.details?.lineItems ?? []) {
    result.set(item.price.id, {
      priceId: item.price.id,
      formattedTotals: item.formattedTotals,
      currencyCode: response.data.currencyCode,
    });
  }

  return result;
}

// ─── Checkout ─────────────────────────────────────────────────────────────────

export interface CheckoutOptions {
  priceId: string;
  userEmail?: string;
  firebaseUid?: string;
  customerPaddleId?: string;
}

export async function openPaddleCheckout(opts: CheckoutOptions): Promise<void> {
  await initPaddle(opts.userEmail);

  if (!window.Paddle) throw new Error("[Paddle] SDK not initialised");

  window.Paddle.Checkout.open({
    items: [{ priceId: opts.priceId, quantity: 1 }],
    customer: opts.userEmail ? { email: opts.userEmail } : undefined,
    customData: {
      firebase_uid: opts.firebaseUid ?? "",
      email: opts.userEmail ?? "",
      source: "vidrank_landing",
    },
    settings: {
      displayMode: "overlay",
      variant: "one-page",
      theme: "dark",
      locale: "en",
      successUrl: `${window.location.origin}/welcome`,
    },
  });
}
