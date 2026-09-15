CREATE TABLE IF NOT EXISTS portfolio_reports (
    owner_id TEXT NOT NULL,
    data_mode TEXT NOT NULL CHECK (data_mode IN ('LIVE', 'MOCK')),
    report_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, data_mode, report_id)
);
