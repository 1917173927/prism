"""Owner-scoped immutable versions shared by the research lab features."""
from datetime import UTC, datetime
from hashlib import sha256
import json
import re

from app.store.sqlite import StoreConflictError, StoreCorruptError, _validate_owner


class LabNotFound(ValueError):
    pass


class LabInvalid(ValueError):
    pass


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False, default=str).encode()).hexdigest()


class LabRecords:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))

    def _read(self, row):
        if row is None:
            raise LabNotFound("研究记录不存在或不可访问。")
        payload = json.loads(row["payload_json"])
        if digest(payload) != row["content_hash"]:
            raise StoreCorruptError("research lab record failed integrity check")
        return {"record_id": row["record_id"], "revision": row["revision"], "saved_at": row["created_at"], "payload": payload}

    def get(self, owner, kind, record_id, revision=None):
        _validate_owner(owner)
        with self.store._lock:
            row = self.store._connection.execute(
                "SELECT * FROM research_lab_versions WHERE owner_id=? AND kind=? AND record_id=?" +
                (" AND revision=?" if revision is not None else " ORDER BY revision DESC LIMIT 1"),
                (owner, kind, record_id, revision) if revision is not None else (owner, kind, record_id)).fetchone()
        return self._read(row)

    def list(self, owner, kind):
        _validate_owner(owner)
        with self.store._lock:
            rows = self.store._connection.execute(
                "SELECT v.* FROM research_lab_versions v WHERE v.owner_id=? AND v.kind=? AND v.revision=(SELECT MAX(p.revision) FROM research_lab_versions p WHERE p.owner_id=v.owner_id AND p.kind=v.kind AND p.record_id=v.record_id) ORDER BY v.created_at DESC,v.record_id", (owner, kind)).fetchall()
        return [self._read(row) for row in rows]

    def write(self, owner, kind, record_id, expected_revision, payload):
        _validate_owner(owner)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", record_id):
            raise LabInvalid("记录编号格式不正确。")
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False, default=str)
        if len(raw.encode()) > 2_000_000:
            raise LabInvalid("记录过大，请缩小研究范围。")
        with self.store._lock:
            connection = self.store._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT MAX(revision) AS revision FROM research_lab_versions WHERE owner_id=? AND kind=? AND record_id=?", (owner, kind, record_id)).fetchone()
                revision = row["revision"] or 0
                if revision != expected_revision:
                    raise StoreConflictError("研究记录已变化，请刷新后操作。")
                if revision == 0 and len(self.list(owner, kind)) >= 200:
                    raise LabInvalid("该类记录已达到200条上限。")
                connection.execute("INSERT INTO research_lab_versions VALUES (?,?,?,?,?,?,?)", (owner, kind, record_id, revision+1, raw, digest(json.loads(raw)), self.clock().isoformat()))
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return self.get(owner, kind, record_id, revision+1)
