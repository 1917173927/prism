CREATE TABLE questionnaire_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    snapshot_version INTEGER NOT NULL,
    ruleset_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    confirmed_at TEXT NOT NULL,
    UNIQUE (owner_id, snapshot_version)
);

CREATE INDEX idx_questionnaire_snapshots_owner_confirmed
    ON questionnaire_snapshots (owner_id, confirmed_at DESC, snapshot_version DESC);

INSERT INTO behavior_rule_versions (ruleset_version, config_json, created_at)
VALUES (
    'investor-questionnaire-rules.v1',
    '{"questionnaire_version":"investor-questionnaire.v1","required_questions":19,"dimensions":["risk","exp","act","res","inf","ai","per","aid"],"suitability":{"C1":[0,24],"C2":[25,44],"C3":[45,64],"C4":[65,81],"C5":[82,100]}}',
    '2026-09-08T00:00:00+00:00'
);
