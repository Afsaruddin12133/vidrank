-- Paddle Billing Fulfillment Tables: customers and subscriptions

CREATE TABLE IF NOT EXISTS customers (
  customer_id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);

-- Add Paddle specific columns to existing subscriptions table if not present
ALTER TABLE subscriptions ADD COLUMN customer_id TEXT;
ALTER TABLE subscriptions ADD COLUMN price_id TEXT;
ALTER TABLE subscriptions ADD COLUMN product_id TEXT;
ALTER TABLE subscriptions ADD COLUMN scheduled_change_action TEXT;
ALTER TABLE subscriptions ADD COLUMN scheduled_change_at TIMESTAMP;
ALTER TABLE subscriptions ADD COLUMN updated_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_subscriptions_customer_id ON subscriptions(customer_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
