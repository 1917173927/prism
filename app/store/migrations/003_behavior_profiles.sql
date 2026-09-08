CREATE TABLE IF NOT EXISTS behavior_events (
    event_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('TRADE', 'POSITION_SNAPSHOT')),
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_behavior_events_owner_occurred
    ON behavior_events (owner_id, occurred_at ASC, event_id ASC);

CREATE TABLE IF NOT EXISTS behavior_profiles (
    behavior_profile_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL,
    ruleset_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    calculated_at TEXT NOT NULL,
    UNIQUE (owner_id, profile_version)
);

CREATE INDEX IF NOT EXISTS idx_behavior_profiles_owner_calculated
    ON behavior_profiles (owner_id, calculated_at DESC, behavior_profile_id DESC);

CREATE TABLE IF NOT EXISTS display_policies (
    owner_id TEXT PRIMARY KEY,
    trust_score INTEGER NOT NULL CHECK (trust_score BETWEEN 0 AND 100),
    mode TEXT NOT NULL CHECK (mode IN ('AUDIT_EXPANDED', 'STANDARD', 'CONCLUSION_FIRST')),
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_ocr_confirmations (
    confirmation_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    image_digest TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    UNIQUE (owner_id, image_digest)
);

CREATE INDEX IF NOT EXISTS idx_ocr_confirmations_owner_confirmed
    ON portfolio_ocr_confirmations (owner_id, confirmed_at DESC, confirmation_id DESC);
