"""Versioned registration of reviewed API adapters, never executable packages."""
from __future__ import annotations

from datetime import UTC, datetime
from contextvars import ContextVar
import json
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.providers.contracts import ProviderOperation, ProviderRequest, ProviderResult, ProviderIssue, ProviderIssueCode
from app.providers.fingerprint import compute_request_fingerprint
from app.providers.skillhub import load_iwencai_skill_manifest
from app.store.sqlite import StoreConflictError


class SkillUnavailable(ValueError):
    """A registered capability cannot currently execute."""


class SkillMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    skill_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,99}$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    name: str = Field(min_length=1, max_length=100)
    operation: ProviderOperation
    endpoint: Literal["/v1/query2data", "/v1/comprehensive/search"]
    channel: Literal["announcement", "news", "report"] | None = None
    package_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def reviewed_route(self):
        routes = load_iwencai_skill_manifest()["skills"]
        if not any((row["operation"], row["endpoint"], row.get("channel")) ==
                   (self.operation.value, self.endpoint, self.channel) for row in routes):
            raise ValueError("capability must use a reviewed operation and endpoint")
        return self


class SkillRegistry:
    """Thin repository over the shared store's portable transaction boundary."""

    def __init__(self, store, *, clock: Callable[[], datetime] | None = None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))
        with self.store._lock:
            connection = self.store._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                # Existing bundled adapters are available under the existing
                # provider-authentication gate. New versions require a probe.
                for row in load_iwencai_skill_manifest()["skills"]:
                    metadata = SkillMetadata.model_validate(row)
                    existing = connection.execute(
                        "SELECT version FROM skill_versions WHERE skill_id=? LIMIT 1",
                        (metadata.skill_id,),
                    ).fetchone()
                    if existing is None:
                        connection.execute(
                            "INSERT INTO skill_versions VALUES (?,?,?,?,?,?,?)",
                            (metadata.skill_id, metadata.version, metadata.model_dump_json(),
                             "INSTALLED", 1, 1, self._now()),
                        )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def _now(self):
        return self.clock().isoformat()

    @staticmethod
    def _view(row):
        metadata = json.loads(row["metadata_json"])
        return {**metadata, "status": row["status"], "enabled": bool(row["enabled"]),
                "revision": row["revision"], "updated_at": row["updated_at"],
                "execution_mode": "CONTROLLED_API_ADAPTER",
                "package_integrity": "REGISTERED_HASH_ONLY" if metadata.get("package_sha256") else "NOT_PROVIDED"}

    def list(self, owner_id: str | None = None):
        with self.store._lock:
            rows = self.store._connection.execute(
                "SELECT * FROM skill_versions ORDER BY skill_id,version"
            ).fetchall()
            selections = {} if owner_id is None else {
                row["skill_id"]: row for row in self.store._connection.execute(
                    "SELECT * FROM skill_selections WHERE owner_id=?", (owner_id,)
                ).fetchall()
            }
        items = []
        for row in rows:
            item = self._view(row)
            chosen = selections.get(item["skill_id"])
            item["personal_enabled"] = bool(chosen["enabled"]) if chosen else True
            item["selection_revision"] = chosen["revision"] if chosen else 0
            item["callable"] = item["status"] == "INSTALLED" and item["enabled"] and item["personal_enabled"]
            items.append(item)
        return items

    def get(self, skill_id, version):
        with self.store._lock:
            row = self.store._connection.execute(
                "SELECT * FROM skill_versions WHERE skill_id=? AND version=?", (skill_id, version)
            ).fetchone()
        if row is None:
            raise SkillUnavailable("capability version is unavailable")
        return self._view(row)

    def _write(self, action):
        with self.store._lock:
            connection = self.store._connection
            connection.execute("BEGIN IMMEDIATE")
            try:
                result = action(connection)
                connection.execute("COMMIT")
                return result
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def install(self, metadata: SkillMetadata, expected_revision: int = 0):
        def write(connection):
            row = connection.execute("SELECT * FROM skill_versions WHERE skill_id=? AND version=?",
                                     (metadata.skill_id, metadata.version)).fetchone()
            revision = row["revision"] if row else 0
            if revision != expected_revision:
                raise StoreConflictError("capability revision changed")
            if row and row["status"] != "UNINSTALLED":
                raise StoreConflictError("capability version is already registered")
            values = (metadata.model_dump_json(), "PENDING", 0, revision + 1, self._now())
            if row:
                connection.execute("UPDATE skill_versions SET metadata_json=?,status=?,enabled=?,revision=?,updated_at=? WHERE skill_id=? AND version=?",
                                   (*values, metadata.skill_id, metadata.version))
            else:
                connection.execute("INSERT INTO skill_versions VALUES (?,?,?,?,?,?,?)",
                                   (metadata.skill_id, metadata.version, *values))
        self._write(write)
        return self.get(metadata.skill_id, metadata.version)

    def update(self, skill_id, version, *, action: str, expected_revision: int):
        def write(connection):
            row = connection.execute("SELECT * FROM skill_versions WHERE skill_id=? AND version=?",
                                     (skill_id, version)).fetchone()
            if row is None or row["revision"] != expected_revision:
                raise StoreConflictError("capability revision changed")
            status, enabled = row["status"], row["enabled"]
            if action == "uninstall":
                status, enabled = "UNINSTALLED", 0
            elif action == "disable":
                enabled = 0
            elif action in {"enable", "verified"}:
                if action == "enable" and status != "INSTALLED":
                    raise SkillUnavailable("capability version must pass verification first")
                if action == "verified" and status != "PENDING":
                    raise SkillUnavailable("only a pending version can be verified")
                # Activating a version disables the previous version atomically.
                connection.execute("UPDATE skill_versions SET enabled=0,revision=revision+1,updated_at=? WHERE skill_id=? AND version<>? AND enabled=1",
                                   (self._now(), skill_id, version))
                status, enabled = "INSTALLED", 1
            else:
                raise ValueError("unknown capability action")
            connection.execute("UPDATE skill_versions SET status=?,enabled=?,revision=?,updated_at=? WHERE skill_id=? AND version=?",
                               (status, enabled, expected_revision + 1, self._now(), skill_id, version))
        self._write(write)
        return self.get(skill_id, version)

    def select(self, owner_id, skill_id, *, enabled: bool, expected_revision: int):
        def write(connection):
            if connection.execute("SELECT skill_id FROM skill_versions WHERE skill_id=? AND status<>? LIMIT 1",
                                  (skill_id, "UNINSTALLED")).fetchone() is None:
                raise SkillUnavailable("capability is unavailable")
            row = connection.execute("SELECT * FROM skill_selections WHERE owner_id=? AND skill_id=?",
                                     (owner_id, skill_id)).fetchone()
            revision = row["revision"] if row else 0
            if revision != expected_revision:
                raise StoreConflictError("personal capability revision changed")
            values = (int(enabled), revision + 1, self._now())
            if row:
                connection.execute("UPDATE skill_selections SET enabled=?,revision=?,updated_at=? WHERE owner_id=? AND skill_id=?",
                                   (*values, owner_id, skill_id))
            else:
                connection.execute("INSERT INTO skill_selections VALUES (?,?,?,?,?)", (owner_id, skill_id, *values))
        self._write(write)
        return {"skill_id": skill_id, "enabled": enabled, "revision": expected_revision + 1}

    def resolve(self, request: ProviderRequest, owner_id: str | None = None):
        channel = str(request.parameters.get("channel", "announcement")).lower()
        candidates = [row for row in self.list(owner_id) if row["callable"] and
                      row["operation"] == request.operation.value and
                      (request.operation != ProviderOperation.SEARCH_NEWS or row.get("channel") == channel)]
        # Prefer the established adapter ID if an additional adapter supports
        # the same route. Explicit selection is reserved for the probe path.
        trusted_ids = [row["skill_id"] for row in load_iwencai_skill_manifest()["skills"]]
        candidates.sort(key=lambda row: (row["skill_id"] not in trusted_ids, row["skill_id"]))
        if not candidates:
            raise SkillUnavailable("capability is disabled or unavailable for this user")
        return SkillMetadata.model_validate({key: candidates[0][key] for key in SkillMetadata.model_fields})

    def scoped_provider(self, provider, owner_id: str, *, skill_id=None, version=None):
        if (skill_id is None) != (version is None):
            raise ValueError("an exact capability requires both ID and version")
        registry = self
        captured = ContextVar("prism_skill_snapshot", default=None)

        class ScopedProvider:
            def __getattr__(self, name):
                return getattr(provider, name)

            @property
            def name(self):
                return provider.name

            @property
            def captured_skill(self):
                snapshot = captured.get()
                return dict(snapshot) if snapshot is not None else None

            async def execute(self, request: ProviderRequest) -> ProviderResult:
                try:
                    if skill_id is None:
                        metadata = registry.resolve(request, owner_id)
                    else:
                        row = next((item for item in registry.list(owner_id)
                                    if item["skill_id"] == skill_id and item["version"] == version
                                    and item["callable"]), None)
                        channel = str(request.parameters.get("channel", "announcement")).lower()
                        if row is None or row["operation"] != request.operation.value or (
                            request.operation == ProviderOperation.SEARCH_NEWS and row.get("channel") != channel
                        ):
                            raise SkillUnavailable("selected capability does not permit this operation")
                        metadata = SkillMetadata.model_validate({key: row[key] for key in SkillMetadata.model_fields})
                    captured.set(metadata.model_dump(mode="json", exclude_none=True))
                except SkillUnavailable:
                    captured.set(None)
                    return ProviderResult(request_id=request.request_id,
                        request_fingerprint=compute_request_fingerprint(request), provider=provider.name,
                        status="FAILED", retrieved_at=registry.clock(),
                        issues=(ProviderIssue(code=ProviderIssueCode.PERMISSION_DENIED, stage="skill_selection",
                            safe_message="技能尚未安装、已停用或未在当前账户启用。", retriable=False),))
                if hasattr(provider, "bind_registry"):
                    return await provider.execute(request, skill=metadata.model_dump(mode="json", exclude_none=True))
                return await provider.execute(request)

        return ScopedProvider()

    async def probe(self, skill_id, version, *, expected_revision: int, provider):
        row = self.get(skill_id, version)
        if row["revision"] != expected_revision:
            raise StoreConflictError("capability revision changed")
        if row["status"] != "PENDING":
            raise SkillUnavailable("only pending versions need verification")
        queries = {"MARKET_DATA": "贵州茅台最新价", "COMPANY_DATA": "贵州茅台营业收入",
                   "INDUSTRY_DATA": "白酒行业市盈率", "MACRO_DATA": "中国最新CPI同比",
                   "FUND_DATA": "沪深300ETF最新净值", "CONVERTIBLE_BOND_DATA": "可转债价格低于130元",
                   "SEARCH_NEWS": "贵州茅台最新公告", "SEARCH_REPORTS": "贵州茅台最新研报"}
        metadata = SkillMetadata.model_validate({key: row[key] for key in SkillMetadata.model_fields})
        parameters = {"limit": 1}
        if metadata.channel:
            parameters["channel"] = metadata.channel
        request = ProviderRequest(request_id=f"skill-probe:{skill_id}:{version}",
                                  operation=metadata.operation, subject=queries[metadata.operation.value], parameters=parameters)
        result = await provider.execute(request, skill=metadata.model_dump(mode="json", exclude_none=True))
        # A connection or a non-empty scalar response cannot validate the
        # reviewed adapter's row contract. Zero is an eligible observed value.
        def valid_rows(items):
            return isinstance(items, (tuple, list)) and bool(items) and all(
                isinstance(item, dict) and bool(item) and any(
                    value is not None and value != "" for value in item.values()
                ) for item in items
            )

        passed = result.status.value in {"SUCCESS", "PARTIAL"} and any(
            valid_rows(record.fields.get("items")) for record in result.records)
        if passed:
            row = self.update(skill_id, version, action="verified", expected_revision=expected_revision)
        return {"status": "PASS" if passed else "FAILED", "skill": row,
                "provider_status": result.status.value,
                "error_code": result.issues[0].code.value if result.issues else None}
