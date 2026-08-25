-- Migration 008: Paddle payments / transactions table
CREATE TABLE IF NOT EXISTS payments (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    subscription_id TEXT,
    user_id TEXT,
    email TEXT,
    amount_cents INTEGER NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL,
    card_brand TEXT,
    card_last4 TEXT,
    invoice_id TEXT,
    invoice_number TEXT,
    billed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payments_customer ON payments (customer_id);
CREATE INDEX IF NOT EXISTS idx_payments_subscription ON payments (subscription_id);
CREATE INDEX IF NOT EXISTS idx_payments_email ON payments (email);
CREATE INDEX IF NOT EXISTS idx_payments_user ON payments (user_id);
