CREATE TABLE behavior_events_owner_scoped (
    event_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('TRADE', 'POSITION_SNAPSHOT')),
    content_hash TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    PRIMARY KEY (owner_id, event_id)
);

INSERT INTO behavior_events_owner_scoped
    (event_id, owner_id, event_type, content_hash, payload_json, occurred_at)
SELECT event_id, owner_id, event_type, content_hash, payload_json, occurred_at
FROM behavior_events;

DROP TABLE behavior_events;

ALTER TABLE behavior_events_owner_scoped RENAME TO behavior_events;

CREATE INDEX idx_behavior_events_owner_occurred
    ON behavior_events (owner_id, occurred_at ASC, event_id ASC);

CREATE TABLE behavior_rule_versions (
    ruleset_version TEXT PRIMARY KEY,
    config_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

INSERT INTO behavior_rule_versions (ruleset_version, config_json, created_at)
VALUES (
    'behavior-profile-rules.v1',
    '{"display_policy":{"audit_expanded_max":34,"conclusion_first_min":65},"minimum_evidence":{"position_snapshots":2,"trades":3},"suitability":{"C1":[0,24],"C2":[25,44],"C3":[45,64],"C4":[65,81],"C5":[82,100]}}',
    '2026-09-08T00:00:00+00:00'
);
