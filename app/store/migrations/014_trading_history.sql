CREATE TABLE IF NOT EXISTS trade_import_batches (
    owner_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_digest TEXT NOT NULL,
    source_type TEXT NOT NULL CHECK (source_type IN ('CSV', 'XLSX', 'IMAGE')),
    payload_json TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, batch_id),
    UNIQUE (owner_id, source_digest)
);

CREATE INDEX IF NOT EXISTS idx_trade_batches_owner_confirmed
    ON trade_import_batches (owner_id, confirmed_at DESC, batch_id DESC);

CREATE TABLE IF NOT EXISTS trade_record_revisions (
    owner_id TEXT NOT NULL,
    trade_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision >= 1),
    batch_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'WITHDRAWN')),
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, trade_id, revision),
    FOREIGN KEY (owner_id, batch_id) REFERENCES trade_import_batches(owner_id, batch_id)
);

CREATE INDEX IF NOT EXISTS idx_trade_revisions_owner_time
    ON trade_record_revisions (owner_id, updated_at DESC, trade_id, revision DESC);

CREATE TABLE IF NOT EXISTS trading_style_profiles (
    owner_id TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    profile_version INTEGER NOT NULL CHECK (profile_version >= 1),
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    calculated_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, profile_id),
    UNIQUE (owner_id, profile_version)
);

CREATE INDEX IF NOT EXISTS idx_trading_style_owner_version
    ON trading_style_profiles (owner_id, profile_version DESC, calculated_at DESC);
