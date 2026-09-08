CREATE TABLE IF NOT EXISTS access_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT,
    method TEXT NOT NULL,
    route TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS access_audit_owner ON access_audit(owner_id, audit_id);
