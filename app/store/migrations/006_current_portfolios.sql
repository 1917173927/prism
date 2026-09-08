CREATE TABLE IF NOT EXISTS current_portfolios (
    owner_id TEXT NOT NULL,
    data_mode TEXT NOT NULL CHECK (data_mode IN ('LIVE', 'MOCK')),
    payload_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    PRIMARY KEY (owner_id, data_mode)
);
