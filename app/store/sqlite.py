"""SQLite implementation of the owner-scoped decision-event store port."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Protocol

from app.store.contracts import (
    DecisionEvent,
    DecisionEventSummary,
    event_content_payload,
)
from app.store.context import ContextMemoryRecord
from app.profile import BehaviorEvent, BehaviorProfile, DisplayPolicy
from app.portfolio import PortfolioOcrConfirmation


class StoreError(RuntimeError):
    """Base class for safe persistence failures."""


class StoreConflictError(StoreError):
    """A stable event identity already carries different content."""


class StoreOwnerError(StoreError):
    """The caller attempted a write outside the event owner scope."""


class StoreCorruptError(StoreError):
    """A stored row failed contract or content validation."""


class ContextMemoryConflictError(StoreConflictError):
    """A context-memory identity already carries different content."""


class ContextMemoryCorruptError(StoreCorruptError):
    """A context-memory row failed integrity validation."""


class DecisionEventStore(Protocol):
    def save(self, event: DecisionEvent) -> tuple[DecisionEvent, bool]: ...

    def get(self, owner_id: str, event_id: str) -> DecisionEvent | None: ...

    def list(self, owner_id: str) -> tuple[DecisionEventSummary, ...]: ...

    def save_context_memory(
        self, record: ContextMemoryRecord
    ) -> tuple[ContextMemoryRecord, bool]: ...

    def get_context_memory(
        self, owner_id: str, memory_id: str
    ) -> ContextMemoryRecord | None: ...

    def list_context_memory(
        self, owner_id: str, limit: int = 20
    ) -> tuple[ContextMemoryRecord, ...]: ...

    def close(self) -> None: ...

    def save_behavior_events(
        self, owner_id: str, events: tuple[BehaviorEvent, ...]
    ) -> tuple[tuple[BehaviorEvent, ...], int]: ...

    def list_behavior_events(self, owner_id: str) -> tuple[BehaviorEvent, ...]: ...

    def save_behavior_profile(self, profile: BehaviorProfile) -> BehaviorProfile: ...

    def get_latest_behavior_profile(self, owner_id: str) -> BehaviorProfile | None: ...

    def save_display_policy(self, policy: DisplayPolicy) -> DisplayPolicy: ...

    def get_display_policy(self, owner_id: str) -> DisplayPolicy | None: ...

    def save_portfolio_ocr_confirmation(
        self, record: PortfolioOcrConfirmation
    ) -> tuple[PortfolioOcrConfirmation, bool]: ...


_MIGRATION_DIR = Path(__file__).parent / "migrations"


def _canonical_event_json(event: DecisionEvent) -> str:
    return json.dumps(
        event.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_context_memory_json(record: ContextMemoryRecord) -> str:
    return json.dumps(
        record.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_contract_json(record: object) -> str:
    return json.dumps(
        record.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _content_hash(record: object) -> str:
    from hashlib import sha256

    return sha256(_canonical_contract_json(record).encode("utf-8")).hexdigest()


def _validate_owner(owner_id: str) -> str:
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise StoreOwnerError("owner scope is required")
    normalized = owner_id.strip()
    lowered = normalized.casefold().replace("-", "_")
    if any(
        token in lowered
        for token in (
            "api_key",
            "apikey",
            "authorization",
            "password",
            "private_key",
            "secret",
            "token",
            "credential",
            "cookie",
        )
    ):
        raise StoreOwnerError("owner scope is not allowed")
    return normalized


class SQLiteDecisionEventStore:
    """Transactional local store; callers must inject the path explicitly."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        if not isinstance(database, (str, Path)):
            raise TypeError("database must be a path or :memory:")
        self._database = str(database)
        if self._database != ":memory:":
            path = Path(self._database)
            if not path.parent.exists():
                raise FileNotFoundError("database parent directory does not exist")
        self._lock = RLock()
        self._connection = sqlite3.connect(
            self._database,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute("PRAGMA foreign_keys = ON")
            if self._database != ":memory:":
                self._connection.execute("PRAGMA journal_mode = WAL")
            self._connection.execute("PRAGMA busy_timeout = 3000")
            self._run_migrations()

    def _run_migrations(self) -> None:
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        applied = {
            int(row["version"])
            for row in self._connection.execute(
                "SELECT version FROM schema_migrations"
            ).fetchall()
        }
        migration_files = sorted(_MIGRATION_DIR.glob("*.sql"))
        for migration_file in migration_files:
            version = int(migration_file.name.split("_", 1)[0])
            if version in applied:
                continue
            script = migration_file.read_text(encoding="utf-8")
            try:
                self._connection.executescript(script)
                self._connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (version, datetime.now(UTC).isoformat()),
                )
            except Exception:
                raise

    @staticmethod
    def _parse_row(row: sqlite3.Row) -> DecisionEvent:
        try:
            payload = json.loads(row["payload_json"])
            event = DecisionEvent.model_validate(payload)
            if (
                event.event_id != row["event_id"]
                or event.owner_id != row["owner_id"]
                or event.composition_id != row["composition_id"]
                or event.status.value != row["status"]
                or event.receipt_id != row["receipt_id"]
            ):
                raise ValueError("row identity does not match payload")
            if event.content_hash != row["content_hash"]:
                raise ValueError("row hash does not match payload")
            if event.recorded_at.isoformat() != row["recorded_at"]:
                raise ValueError("row timestamp does not match payload")
            return event
        except Exception as exc:
            raise StoreCorruptError("stored decision event failed validation") from exc

    def save(self, event: DecisionEvent) -> tuple[DecisionEvent, bool]:
        try:
            normalized = DecisionEvent.model_validate(event.model_dump(mode="python"))
        except Exception as exc:
            raise StoreCorruptError("decision event failed contract validation") from exc
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT * FROM decision_events WHERE event_id = ?",
                    (normalized.event_id,),
                ).fetchone()
                if row is not None:
                    existing = self._parse_row(row)
                    if existing.owner_id != normalized.owner_id:
                        raise StoreConflictError("event identity belongs to another owner")
                    if existing.content_hash != normalized.content_hash:
                        raise StoreConflictError("event identity already has different content")
                    self._connection.execute("COMMIT")
                    return existing, False
                self._connection.execute(
                    """
                    INSERT INTO decision_events
                        (event_id, owner_id, composition_id, status, receipt_id,
                         content_hash, payload_json, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized.event_id,
                        normalized.owner_id,
                        normalized.composition_id,
                        normalized.status.value,
                        normalized.receipt_id,
                        normalized.content_hash,
                        _canonical_event_json(normalized),
                        normalized.recorded_at.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return normalized, True
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def get(self, owner_id: str, event_id: str) -> DecisionEvent | None:
        owner_id = _validate_owner(owner_id)
        if not isinstance(event_id, str) or not event_id.strip():
            raise StoreError("event ID is required")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM decision_events WHERE owner_id = ? AND event_id = ?",
                (owner_id, event_id.strip()),
            ).fetchone()
        return self._parse_row(row) if row is not None else None

    def list(self, owner_id: str) -> tuple[DecisionEventSummary, ...]:
        owner_id = _validate_owner(owner_id)
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM decision_events WHERE owner_id = ?",
                (owner_id,),
            ).fetchall()
        events = [self._parse_row(row) for row in rows]
        events.sort(
            key=lambda event: (event.recorded_at.astimezone(UTC), event.event_id),
            reverse=True,
        )
        summaries: list[DecisionEventSummary] = []
        for event in events:
            summaries.append(
                DecisionEventSummary(
                    event_id=event.event_id,
                    owner_id=event.owner_id,
                    composition_id=event.composition_id,
                    status=event.status,
                    receipt_id=event.receipt_id,
                    recorded_at=event.recorded_at,
                    content_hash=event.content_hash,
                )
            )
        return tuple(summaries)

    @staticmethod
    def _parse_context_memory_row(row: sqlite3.Row) -> ContextMemoryRecord:
        try:
            payload = json.loads(row["payload_json"])
            record = ContextMemoryRecord.model_validate(payload)
            if (
                record.memory_id != row["memory_id"]
                or record.owner_id != row["owner_id"]
                or record.source.value != row["source"]
                or record.content_hash != row["content_hash"]
                or record.saved_at.isoformat() != row["saved_at"]
            ):
                raise ValueError("row identity does not match payload")
            return record
        except Exception as exc:
            raise ContextMemoryCorruptError(
                "stored context memory failed validation"
            ) from exc

    @staticmethod
    def _validate_context_memory_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise StoreError("context memory limit must be between 1 and 100")
        return limit

    def save_context_memory(
        self, record: ContextMemoryRecord
    ) -> tuple[ContextMemoryRecord, bool]:
        try:
            normalized = ContextMemoryRecord.model_validate(
                record.model_dump(mode="python")
            )
            _validate_owner(normalized.owner_id)
        except StoreError:
            raise
        except Exception as exc:
            raise StoreCorruptError(
                "context memory failed contract validation"
            ) from exc
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT * FROM context_memory WHERE memory_id = ?",
                    (normalized.memory_id,),
                ).fetchone()
                if row is not None:
                    existing = self._parse_context_memory_row(row)
                    if existing.owner_id != normalized.owner_id:
                        raise ContextMemoryConflictError(
                            "context memory identity belongs to another owner"
                        )
                    if existing.content_hash != normalized.content_hash:
                        raise ContextMemoryConflictError(
                            "context memory identity already has different content"
                        )
                    self._connection.execute("COMMIT")
                    return existing, False
                self._connection.execute(
                    """
                    INSERT INTO context_memory
                        (memory_id, owner_id, source, content_hash, payload_json, saved_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized.memory_id,
                        normalized.owner_id,
                        normalized.source.value,
                        normalized.content_hash,
                        _canonical_context_memory_json(normalized),
                        normalized.saved_at.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return normalized, True
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def get_context_memory(
        self, owner_id: str, memory_id: str
    ) -> ContextMemoryRecord | None:
        owner_id = _validate_owner(owner_id)
        if not isinstance(memory_id, str) or not memory_id.strip():
            raise StoreError("memory ID is required")
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM context_memory WHERE owner_id = ? AND memory_id = ?",
                (owner_id, memory_id.strip()),
            ).fetchone()
        return self._parse_context_memory_row(row) if row is not None else None

    def list_context_memory(
        self, owner_id: str, limit: int = 20
    ) -> tuple[ContextMemoryRecord, ...]:
        owner_id = _validate_owner(owner_id)
        limit = self._validate_context_memory_limit(limit)
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM context_memory
                WHERE owner_id = ?
                """,
                (owner_id,),
            ).fetchall()
        records = [self._parse_context_memory_row(row) for row in rows]
        records.sort(
            key=lambda record: (record.saved_at.astimezone(UTC), record.memory_id),
            reverse=True,
        )
        return tuple(records[:limit])

    @staticmethod
    def _parse_behavior_event_row(row: sqlite3.Row) -> BehaviorEvent:
        try:
            event = BehaviorEvent.model_validate(json.loads(row["payload_json"]))
            if (
                event.event_id != row["event_id"]
                or event.owner_id != row["owner_id"]
                or event.event_type.value != row["event_type"]
                or event.occurred_at.isoformat() != row["occurred_at"]
                or _content_hash(event) != row["content_hash"]
            ):
                raise ValueError("row identity does not match payload")
            return event
        except Exception as exc:
            raise StoreCorruptError("stored behavior event failed validation") from exc

    def save_behavior_events(
        self, owner_id: str, events: tuple[BehaviorEvent, ...]
    ) -> tuple[tuple[BehaviorEvent, ...], int]:
        owner_id = _validate_owner(owner_id)
        normalized = tuple(
            BehaviorEvent.model_validate(item.model_dump(mode="python")) for item in events
        )
        if any(item.owner_id != owner_id for item in normalized):
            raise StoreOwnerError("behavior event owner does not match owner scope")
        if len({item.event_id for item in normalized}) != len(normalized):
            raise StoreConflictError("behavior event batch contains duplicate IDs")
        created = 0
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for event in normalized:
                    row = self._connection.execute(
                        "SELECT * FROM behavior_events WHERE owner_id = ? AND event_id = ?",
                        (owner_id, event.event_id),
                    ).fetchone()
                    if row is not None:
                        existing = self._parse_behavior_event_row(row)
                        if _content_hash(existing) != _content_hash(event):
                            raise StoreConflictError("behavior event identity already has different content")
                        continue
                    self._connection.execute(
                        """
                        INSERT INTO behavior_events
                            (event_id, owner_id, event_type, content_hash, payload_json, occurred_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event.event_id,
                            event.owner_id,
                            event.event_type.value,
                            _content_hash(event),
                            _canonical_contract_json(event),
                            event.occurred_at.isoformat(),
                        ),
                    )
                    created += 1
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return normalized, created

    def list_behavior_events(self, owner_id: str) -> tuple[BehaviorEvent, ...]:
        owner_id = _validate_owner(owner_id)
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM behavior_events WHERE owner_id = ? ORDER BY occurred_at ASC, event_id ASC",
                (owner_id,),
            ).fetchall()
        return tuple(self._parse_behavior_event_row(row) for row in rows)

    def save_behavior_profile(self, profile: BehaviorProfile) -> BehaviorProfile:
        normalized = BehaviorProfile.model_validate(profile.model_dump(mode="python"))
        _validate_owner(normalized.owner_id)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                existing = self._connection.execute(
                    "SELECT behavior_profile_id, payload_json FROM behavior_profiles WHERE owner_id = ? AND profile_version = ?",
                    (normalized.owner_id, normalized.profile_version),
                ).fetchone()
                if existing is not None:
                    stored = BehaviorProfile.model_validate(json.loads(existing["payload_json"]))
                    if stored != normalized:
                        raise StoreConflictError("behavior profile version already exists")
                    self._connection.execute("COMMIT")
                    return stored
                self._connection.execute(
                    """
                    INSERT INTO behavior_profiles
                        (behavior_profile_id, owner_id, profile_version, ruleset_version, payload_json, calculated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized.behavior_profile_id,
                        normalized.owner_id,
                        normalized.profile_version,
                        normalized.ruleset_version,
                        _canonical_contract_json(normalized),
                        normalized.calculated_at.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
        return normalized

    def get_latest_behavior_profile(self, owner_id: str) -> BehaviorProfile | None:
        owner_id = _validate_owner(owner_id)
        with self._lock:
            row = self._connection.execute(
                """
                SELECT payload_json FROM behavior_profiles
                WHERE owner_id = ? ORDER BY profile_version DESC, calculated_at DESC LIMIT 1
                """,
                (owner_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            profile = BehaviorProfile.model_validate(json.loads(row["payload_json"]))
            if profile.owner_id != owner_id:
                raise ValueError("owner mismatch")
            return profile
        except Exception as exc:
            raise StoreCorruptError("stored behavior profile failed validation") from exc

    def save_display_policy(self, policy: DisplayPolicy) -> DisplayPolicy:
        normalized = DisplayPolicy.model_validate(policy.model_dump(mode="python"))
        _validate_owner(normalized.owner_id)
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO display_policies (owner_id, trust_score, mode, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(owner_id) DO UPDATE SET
                    trust_score = excluded.trust_score,
                    mode = excluded.mode,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    normalized.owner_id,
                    normalized.trust_score,
                    normalized.mode.value,
                    _canonical_contract_json(normalized),
                    normalized.updated_at.isoformat(),
                ),
            )
        return normalized

    def get_display_policy(self, owner_id: str) -> DisplayPolicy | None:
        owner_id = _validate_owner(owner_id)
        with self._lock:
            row = self._connection.execute(
                "SELECT payload_json FROM display_policies WHERE owner_id = ?", (owner_id,)
            ).fetchone()
        if row is None:
            return None
        try:
            policy = DisplayPolicy.model_validate(json.loads(row["payload_json"]))
            if policy.owner_id != owner_id:
                raise ValueError("owner mismatch")
            return policy
        except Exception as exc:
            raise StoreCorruptError("stored display policy failed validation") from exc

    def save_portfolio_ocr_confirmation(
        self, record: PortfolioOcrConfirmation
    ) -> tuple[PortfolioOcrConfirmation, bool]:
        normalized = PortfolioOcrConfirmation.model_validate(record.model_dump(mode="python"))
        _validate_owner(normalized.owner_id)
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT payload_json FROM portfolio_ocr_confirmations WHERE owner_id = ? AND image_digest = ?",
                    (normalized.owner_id, normalized.image_digest),
                ).fetchone()
                if row is not None:
                    existing = PortfolioOcrConfirmation.model_validate(json.loads(row["payload_json"]))
                    if existing.confirmed_payload_hash != normalized.confirmed_payload_hash:
                        raise StoreConflictError("OCR confirmation digest already has different content")
                    self._connection.execute("COMMIT")
                    return existing, False
                self._connection.execute(
                    """
                    INSERT INTO portfolio_ocr_confirmations
                        (confirmation_id, owner_id, image_digest, payload_json, confirmed_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        normalized.confirmation_id,
                        normalized.owner_id,
                        normalized.image_digest,
                        _canonical_contract_json(normalized),
                        normalized.confirmed_at.isoformat(),
                    ),
                )
                self._connection.execute("COMMIT")
                return normalized, True
            except Exception:
                self._connection.execute("ROLLBACK")
                raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()


__all__ = [
    "DecisionEventStore",
    "SQLiteDecisionEventStore",
    "StoreConflictError",
    "ContextMemoryConflictError",
    "ContextMemoryCorruptError",
    "StoreCorruptError",
    "StoreError",
    "StoreOwnerError",
]
