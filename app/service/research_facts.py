"""Immutable, owner-scoped scalar observations with input and response hashes.

Persistence establishes provenance and reproducibility, not source correctness.
Single-source observations are never upgraded to verified financial facts.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re

from app.providers.contracts import ProviderResult
from app.providers.fingerprint import redact_sensitive_data
from app.store.sqlite import StoreCorruptError


METHOD_VERSION = "live-scalar-normalization.v1"


class ResearchFactNotFound(ValueError):
    pass


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _hash(value):
    return sha256(_json(value).encode("utf-8")).hexdigest()


class ResearchFactRepository:
    def __init__(self, store, *, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))
        # A local development build briefly shipped raw columns in migration
        # 020. Preserve those NOT NULL constraints without changing user data;
        # new installations use the separate, portable migration 021 table.
        with store._lock:
            try:
                store._connection.execute("SELECT request_json,response_json FROM research_fact_snapshots LIMIT 0")
                self._legacy_payload_columns = True
            except Exception:
                self._legacy_payload_columns = False

    def save_node(self, *, owner_id, run_id, node_id, request_payload,
                  provider_result: ProviderResult, normalized, input_versions=None):
        if not owner_id or not run_id or normalized.get("node_id") != node_id:
            raise ValueError("research fact input scope mismatch")
        if provider_result.provider.lower().startswith(("fixture", "synthetic", "controlled")):
            raise ValueError("synthetic provider observations cannot enter the LIVE fact repository")
        input_versions = dict(input_versions or {})
        if len(input_versions) > 20 or any(
            not isinstance(key, str) or len(key) > 100 or
            isinstance(value, bool) or not isinstance(value, (str, int)) or len(str(value)) > 256 or
            any(term in (key + str(value)).lower() for term in ("api_key", "authorization", "password", "secret", "bearer"))
            for key, value in input_versions.items()
        ):
            raise ValueError("input versions must contain bounded non-secret version references")
        response_payload = provider_result.model_dump(mode="json")
        for payload in (request_payload, response_payload):
            if redact_sensitive_data(payload) != payload or re.search(
                r"(?:api_key|authorization|password|private_key)\s*[:=]", _json(payload), re.IGNORECASE
            ):
                raise ValueError("raw research snapshots must not contain authentication metadata")
        request_hash = _hash(request_payload)
        response_hash = _hash(response_payload)
        input_versions["research_request_sha256"] = request_hash
        snapshot_id = "rs:" + _hash({"owner": owner_id, "run": run_id, "node": node_id,
            "request": request_hash, "response": response_hash,
            "method": METHOD_VERSION, "inputs": input_versions})
        missing = set(normalized.get("missing_fields", ()))
        facts = []
        for observation in normalized.get("observations", ()):
            if observation.get("verification_status") != "SINGLE_SOURCE_UNVERIFIED":
                raise ValueError("single-source persistence cannot certify an observation")
            source = observation.get("actual_source")
            if not source:
                missing.add("source")
                continue
            try:
                value = Decimal(observation["value"])
                if not value.is_finite():
                    raise ValueError("non-finite observation")
            except (KeyError, TypeError, InvalidOperation):
                raise ValueError("fact value must be a normalized decimal string") from None
            if not isinstance(observation["value"], str):
                raise ValueError("fact values must preserve decimal precision as strings")
            quality = []
            if observation.get("provider_serving_mode") == "CACHE_STALE_FALLBACK":
                quality.append("STALE_SOURCE")
            for field in ("unit", "observed_at"):
                if observation.get(field) is None:
                    quality.append("MISSING_" + field.upper())
            payload = {**observation, "owner_id": owner_id, "run_id": run_id, "node_id": node_id,
                "snapshot_id": snapshot_id, "request_hash": request_hash, "response_hash": response_hash,
                "method_version": METHOD_VERSION, "input_versions": input_versions,
                "quality_issues": quality, "verified": False}
            content_hash = _hash(payload)
            fact_id = "rf:" + content_hash
            facts.append((fact_id, payload, content_hash))
        timestamp = self.clock().isoformat()
        with self.store._lock:
            connection = self.store._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                columns = ["owner_id", "snapshot_id", "run_id", "node_id", "request_hash", "response_hash",
                           "method_version", "input_versions_json", "provider_status", "missing_fields_json", "created_at"]
                values = (owner_id, snapshot_id, run_id, node_id, request_hash, response_hash, METHOD_VERSION,
                          _json(input_versions), provider_result.status.value, _json(sorted(missing)), timestamp)
                if self._legacy_payload_columns:
                    columns.extend(("request_json", "response_json"))
                    values += (_json(request_payload), _json(response_payload))
                connection.execute("INSERT INTO research_fact_snapshots (" + ",".join(columns) + ") VALUES (" +
                    ",".join("?" for _ in columns) + ") ON CONFLICT(owner_id,snapshot_id) DO NOTHING", values)
                connection.execute("INSERT INTO research_fact_payloads (owner_id,snapshot_id,request_json,response_json) VALUES (?,?,?,?) ON CONFLICT(owner_id,snapshot_id) DO NOTHING",
                                   (owner_id, snapshot_id, _json(request_payload), _json(response_payload)))
                for fact_id, payload, content_hash in facts:
                    connection.execute("INSERT INTO research_facts VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(owner_id,fact_id) DO NOTHING",
                        (owner_id, fact_id, snapshot_id, run_id, node_id, _json(payload), content_hash, timestamp))
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return {"snapshot_id": snapshot_id, "fact_refs": [fact_id for fact_id, _, _ in facts],
                "request_hash": request_hash, "response_hash": response_hash,
                "method_version": METHOD_VERSION, "verification_status": "SINGLE_SOURCE_UNVERIFIED" if facts else "NO_VERIFIABLE_OBSERVATION"}

    @staticmethod
    def _fact(row):
        try:
            payload = json.loads(row["fact_json"])
        except (ValueError, TypeError):
            raise StoreCorruptError("stored research observation is invalid") from None
        if (_hash(payload) != row["content_hash"] or row["fact_id"] != "rf:" + row["content_hash"] or
            any(payload.get(key) != row[key] for key in ("owner_id", "run_id", "node_id", "snapshot_id")) or
            payload.get("verified") is not False or payload.get("verification_status") != "SINGLE_SOURCE_UNVERIFIED"):
            raise StoreCorruptError("stored research observation failed integrity checks")
        return {"fact_id": row["fact_id"], **payload, "created_at": row["created_at"]}

    def get(self, owner_id, fact_id):
        with self.store._lock:
            row = self.store._connection.execute("SELECT * FROM research_facts WHERE owner_id=? AND fact_id=?",
                                                (owner_id, fact_id)).fetchone()
        if row is None:
            raise ResearchFactNotFound("research observation is unavailable")
        fact = self._fact(row)
        self.get_snapshot(owner_id, fact["snapshot_id"])
        return fact

    def list_run(self, owner_id, run_id):
        with self.store._lock:
            rows = self.store._connection.execute("SELECT * FROM research_facts WHERE owner_id=? AND run_id=? ORDER BY node_id,fact_id",
                                                 (owner_id, run_id)).fetchall()
        return [self._fact(row) for row in rows]

    def get_snapshot(self, owner_id, snapshot_id):
        with self.store._lock:
            row = self.store._connection.execute("SELECT s.*,p.request_json AS archived_request_json,p.response_json AS archived_response_json FROM research_fact_snapshots s LEFT JOIN research_fact_payloads p ON s.owner_id=p.owner_id AND s.snapshot_id=p.snapshot_id WHERE s.owner_id=? AND s.snapshot_id=?",
                                                (owner_id, snapshot_id)).fetchone()
        if row is None:
            raise ResearchFactNotFound("research input snapshot is unavailable")
        try:
            request_json = row["archived_request_json"]
            response_json = row["archived_response_json"]
            if request_json is None and self._legacy_payload_columns:
                request_json, response_json = row["request_json"], row["response_json"]
            request = json.loads(request_json)
            response = json.loads(response_json)
        except (ValueError, TypeError):
            raise StoreCorruptError("stored research raw snapshot failed integrity checks: raw payload unavailable") from None
        try:
            versions = json.loads(row["input_versions_json"])
        except (ValueError, TypeError):
            raise StoreCorruptError("stored research input versions are invalid") from None
        expected_id = "rs:" + _hash({"owner": owner_id, "run": row["run_id"], "node": row["node_id"],
            "request": row["request_hash"], "response": row["response_hash"],
            "method": row["method_version"], "inputs": versions})
        if (_hash(request) != row["request_hash"] or _hash(response) != row["response_hash"] or
            expected_id != snapshot_id or response.get("status") != row["provider_status"]):
            raise StoreCorruptError("stored research raw snapshot failed integrity checks")
        return {key: row[key] for key in ("owner_id", "snapshot_id", "run_id", "node_id", "request_hash",
                "response_hash", "method_version", "provider_status", "created_at")} | {
                "input_versions": versions,
                "missing_fields": json.loads(row["missing_fields_json"])}
