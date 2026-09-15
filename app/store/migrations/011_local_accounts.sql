CREATE TABLE IF NOT EXISTS local_accounts (
    username TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL UNIQUE,
    salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    admin INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    idle_expires_at TEXT NOT NULL,
    absolute_expires_at TEXT NOT NULL,
    revoked_at TEXT,
    FOREIGN KEY (username) REFERENCES local_accounts(username) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_auth_sessions_owner
ON auth_sessions(owner_id, revoked_at, absolute_expires_at);
