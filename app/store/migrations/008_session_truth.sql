CREATE TABLE IF NOT EXISTS session_truth (
    owner_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, session_id, revision)
);
