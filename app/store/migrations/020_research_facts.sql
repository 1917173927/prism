CREATE TABLE IF NOT EXISTS research_fact_snapshots (
    owner_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_hash TEXT NOT NULL,
    method_version TEXT NOT NULL,
    input_versions_json TEXT NOT NULL,
    provider_status TEXT NOT NULL,
    missing_fields_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, snapshot_id)
);
CREATE TABLE IF NOT EXISTS research_facts (
    owner_id TEXT NOT NULL,
    fact_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    fact_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, fact_id),
    FOREIGN KEY (owner_id, snapshot_id) REFERENCES research_fact_snapshots(owner_id, snapshot_id)
);
CREATE INDEX IF NOT EXISTS ix_research_snapshots_run ON research_fact_snapshots(owner_id, run_id, node_id);
CREATE INDEX IF NOT EXISTS ix_research_facts_run ON research_facts(owner_id, run_id, node_id);
