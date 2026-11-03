CREATE TABLE IF NOT EXISTS research_lab_versions (
    owner_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    record_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, kind, record_id, revision)
);
CREATE INDEX IF NOT EXISTS research_lab_owner_kind ON research_lab_versions(owner_id,kind,created_at);
