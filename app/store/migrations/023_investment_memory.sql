CREATE TABLE IF NOT EXISTS investment_preference_memories (
    owner_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    saved_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, revision)
);
CREATE TABLE IF NOT EXISTS investment_style_policies (
    owner_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, revision)
);
