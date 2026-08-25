/**
 * Paddle Billing — Tier & Price Catalog
 *
 * Edit this file to change plan names, descriptions, features, and price IDs.
 * Price IDs come from your Paddle dashboard (sandbox or live).
 */

export interface Tier {
  name: "Starter" | "Pro" | "Advanced";
  description: string;
  features: string[];
  /** Paddle Price IDs for each billing cycle */
  priceId: { month: string; year: string };
  highlighted?: boolean;
  badge?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// SANDBOX price IDs — swap for live IDs when going to production
// ─────────────────────────────────────────────────────────────────────────────
export const TIERS: Tier[] = [
  {
    name: "Starter",
    description: "For new creators exploring YouTube SEO.",
    features: [
      "50 AI generations per day",
      "YouTube tag generation",
      "YouTube description generation",
      "Basic SEO optimization",
      "Auto-fill tags & descriptions",
      "One-click generation",
      "7-day free trial",
    ],
    priceId: {
      month: "pri_01m0tdmbnpybaffswtpjkkvs4v",
      year: "pri_01m0tdmccj968kmzkpcr1n4b8h",
    },
  },
  {
    name: "Pro",
    description: "For creators ready to grow with intent.",
    features: [
      "Unlimited AI generations",
      "Advanced SEO optimization",
      "Premium AI descriptions & tags",
      "Enhanced keyword targeting",
      "Better discoverability optimization",
      "Faster processing",
      "Early access to new features",
      "Priority support",
      "7-day free trial",
    ],
    priceId: {
      month: "pri_01m0tdmdzab5e2dm36qkahp10e",
      year: "pri_01m0tdmepkt5at1zkpvxqr0sm7",
    },
    highlighted: true,
    badge: "Most Popular",
  },
  {
    name: "Advanced",
    description: "For agencies and power users at scale.",
    features: [
      "Everything in Pro",
      "Unlimited channels",
      "Bulk generation & scheduling",
      "Advanced analytics dashboard",
      "API access",
      "White-label exports",
      "Dedicated account manager",
      "7-day free trial",
    ],
    priceId: {
      month: "pri_01m0tdmfgbzgz1s8wph4qxdbmt",
      year: "pri_01m0tdmg7cfwqjwtcj91ksrycq",
    },
  },
];
