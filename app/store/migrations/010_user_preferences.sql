CREATE TABLE IF NOT EXISTS user_preferences (
    owner_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
