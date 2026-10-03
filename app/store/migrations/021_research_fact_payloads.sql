CREATE TABLE IF NOT EXISTS research_fact_payloads (
    owner_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    request_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    PRIMARY KEY (owner_id, snapshot_id),
    FOREIGN KEY (owner_id, snapshot_id) REFERENCES research_fact_snapshots(owner_id, snapshot_id)
);
