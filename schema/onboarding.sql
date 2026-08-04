CREATE TABLE IF NOT EXISTS onboarding_records (
  onboarding_id TEXT PRIMARY KEY, status TEXT NOT NULL, name TEXT NOT NULL, business_name TEXT NOT NULL,
  email TEXT NOT NULL, phone TEXT NOT NULL, service_area TEXT NOT NULL, service_radius_km INTEGER NOT NULL,
  primary_category TEXT NOT NULL, preferred_services TEXT NOT NULL, work_type TEXT NOT NULL, exclusions TEXT NOT NULL,
  sms_addon INTEGER NOT NULL, category_addon INTEGER NOT NULL, additional_categories TEXT NOT NULL,
  monthly_total_aud INTEGER NOT NULL, stripe_payment_link TEXT NOT NULL, source TEXT NOT NULL, created_at TEXT NOT NULL,
  paid_at TEXT, stripe_checkout_session_id TEXT UNIQUE, stripe_customer_id TEXT, stripe_subscription_id TEXT
);
CREATE INDEX IF NOT EXISTS onboarding_status_idx ON onboarding_records(status);
