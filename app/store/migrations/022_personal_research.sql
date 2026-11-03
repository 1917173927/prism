CREATE TABLE IF NOT EXISTS personal_research_versions (
    owner_id TEXT NOT NULL,
    system_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    definition_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, system_id, revision)
);
CREATE TABLE IF NOT EXISTS personal_research_runs (
    owner_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    system_id TEXT NOT NULL,
    system_revision INTEGER NOT NULL,
    request_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, run_id)
);
CREATE INDEX IF NOT EXISTS personal_research_runs_system ON personal_research_runs(owner_id, system_id, created_at);
