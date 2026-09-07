"""Prism Runtime Mode Controller.

Manages process-level data mode (MOCK vs. LIVE) with concurrency revision locks.
Enforces the core invariant:
"严禁在未接通官方接口时伪造 LIVE 或 FACT CHECKED，未配置凭据时严格处于 MOCK
或 Live 模式下的受控不可用态，坚决杜绝在 Live 失败时静默兜底回退至 Mock。"
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from enum import StrEnum
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class DataMode(StrEnum):
    """Runtime data operation mode."""
    MOCK = "MOCK"
    LIVE = "LIVE"


class ModeRevisionConflictError(Exception):
    """Raised when expected revision does not match current controller revision."""
    pass


class LiveProviderUnavailableError(Exception):
    """Raised when switching to LIVE mode is refused due to missing credentials."""
    pass


class RuntimeModeController:
    """Process-level controller for runtime data mode and revision management."""

    def __init__(self, initial_mode: DataMode | None = None) -> None:
        self._lock = asyncio.Lock()
        self._revision = 1
        self._updated_at = datetime.now(UTC)
        self._fuyao_capabilities = {
            "stock_quote": False,
            "fund_lookthrough": False,
        }
        self._fuyao_capability_checked_at: dict[str, datetime | None] = {
            "stock_quote": None,
            "fund_lookthrough": None,
        }
        self._fuyao_capability_errors: dict[str, str | None] = {
            "stock_quote": None,
            "fund_lookthrough": None,
        }
        self._fuyao_verification = (
            "NOT_CHECKED" if self._fuyao_configured else "UNCONFIGURED"
        )
        self._wencai_available = self._wencai_configured_and_verified
        self._wencai_checked_at: datetime | None = None
        self._wencai_last_error_code: str | None = None
        self._initial_probe_pending = initial_mode is None and self._fuyao_configured

        # Boot mode detection:
        # A non-empty key is configuration evidence, not proof of permissions.
        # The API layer performs a real capability probe before entering LIVE.
        if initial_mode is not None:
            self._mode = initial_mode
        else:
            self._mode = (
                DataMode.LIVE
                if self.is_wencai_ready and not self._fuyao_configured
                else DataMode.MOCK
            )

    @property
    def mode(self) -> DataMode:
        return self._mode

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def updated_at(self) -> datetime:
        return self._updated_at

    @property
    def is_live_ready(self) -> bool:
        """Indicate whether at least one external provider capability is ready."""
        return self.is_fuyao_ready or self.is_wencai_ready

    @property
    def is_fuyao_ready(self) -> bool:
        """Report whether at least one Fuyao capability passed a real probe."""
        return any(self._fuyao_capabilities.values())

    @property
    def _fuyao_configured(self) -> bool:
        return bool(os.getenv("HITHINK_FINANCE_API_KEY", "").strip())

    @property
    def _wencai_ready(self) -> bool:
        return self.is_wencai_ready

    @property
    def is_contract_verified(self) -> bool:
        """Require server-side confirmation of the Wencai response mapping."""
        return os.getenv("WENCAI_SKILLHUB_CONTRACT_VERIFIED", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    @property
    def _wencai_configured_and_verified(self) -> bool:
        return (
            bool(os.getenv("WENCAI_SKILLHUB_API_KEY", "").strip())
            and self.is_contract_verified
        )

    @property
    def is_wencai_ready(self) -> bool:
        """Report Wencai readiness, including observed runtime failures."""
        return self._wencai_available and self._wencai_configured_and_verified

    @property
    def live_readiness_issues(self) -> tuple[str, ...]:
        """List unavailable provider groups without blocking working providers."""
        issues: list[str] = []
        if not any(self._fuyao_capabilities.values()):
            issues.append("FUYAO_MARKET_AND_FUND")
        if not self.is_wencai_ready:
            issues.append("WENCAI_RESEARCH_AND_REFRESH")
        return tuple(issues)

    @property
    def capabilities(self) -> dict[str, Any]:
        """Matrix of feature readiness under MOCK and LIVE modes."""
        live_wencai_ready = self._wencai_ready
        return {
            "MOCK": {
                "stock_quote": True,
                "fund_lookthrough": True,
                "convertible_bond": True,
                "semantic_search": True,
                "portfolio_health_check": True,
                "portfolio_rebalancing": True,
            },
            "LIVE": {
                "stock_quote": self._fuyao_capabilities["stock_quote"],
                "fund_lookthrough": self._fuyao_capabilities["fund_lookthrough"],
                "convertible_bond": live_wencai_ready,
                "market_data": live_wencai_ready,
                "company_data": live_wencai_ready,
                "industry_data": live_wencai_ready,
                "macro_data": live_wencai_ready,
                "fund_data": live_wencai_ready,
                "convertible_bond_data": live_wencai_ready,
                "semantic_search": live_wencai_ready,
                "announcement_search": live_wencai_ready,
                "portfolio_refresh": live_wencai_ready,
                "portfolio_health_check": True,
                "portfolio_rebalancing": True,
            },
        }

    @property
    def needs_initial_probe(self) -> bool:
        return self._initial_probe_pending

    async def apply_fuyao_probe(
        self, capabilities: dict[str, bool], *, auto_activate: bool = False
    ) -> None:
        """Record a real provider probe and optionally activate LIVE once."""
        async with self._lock:
            checked_at = datetime.now(UTC)
            self._fuyao_capabilities = {
                "stock_quote": bool(capabilities.get("stock_quote")),
                "fund_lookthrough": bool(capabilities.get("fund_lookthrough")),
            }
            self._fuyao_capability_checked_at = {
                name: checked_at for name in self._fuyao_capabilities
            }
            self._fuyao_capability_errors = {
                name: None if available else "PROBE_FAILED"
                for name, available in self._fuyao_capabilities.items()
            }
            available_count = sum(self._fuyao_capabilities.values())
            self._fuyao_verification = (
                "VERIFIED" if available_count == len(self._fuyao_capabilities)
                else "DEGRADED" if available_count
                else "FAILED"
            )
            self._initial_probe_pending = False
            if auto_activate and self.is_live_ready and self._mode != DataMode.LIVE:
                self._mode = DataMode.LIVE
                self._revision += 1
            elif not self.is_live_ready and self._mode == DataMode.LIVE:
                self._mode = DataMode.MOCK
                self._revision += 1
            self._updated_at = checked_at

    async def record_fuyao_capability_failure(
        self, capability: str, error_code: str
    ) -> None:
        """Invalidate a failed capability and keep LIVE state internally valid."""
        if capability not in self._fuyao_capabilities:
            raise ValueError(f"Unknown Fuyao capability: {capability}")
        async with self._lock:
            checked_at = datetime.now(UTC)
            self._fuyao_capabilities[capability] = False
            self._fuyao_capability_checked_at[capability] = checked_at
            self._fuyao_capability_errors[capability] = error_code
            available_count = sum(self._fuyao_capabilities.values())
            self._fuyao_verification = "DEGRADED" if available_count else "FAILED"
            if not self.is_live_ready and self._mode == DataMode.LIVE:
                self._mode = DataMode.MOCK
                self._revision += 1
            self._updated_at = checked_at

    async def record_wencai_failure(self, error_code: str) -> None:
        """Invalidate Wencai capabilities after an observed provider failure."""
        async with self._lock:
            checked_at = datetime.now(UTC)
            self._wencai_available = False
            self._wencai_checked_at = checked_at
            self._wencai_last_error_code = error_code
            if not self.is_live_ready and self._mode == DataMode.LIVE:
                self._mode = DataMode.MOCK
                self._revision += 1
            self._updated_at = checked_at

    def get_status(self) -> dict[str, Any]:
        """Return serialized state representation."""
        return {
            "data_mode": self._mode.value,
            "revision": self._revision,
            "live_ready": self.is_live_ready,
            "live_configured": self._fuyao_configured,
            "live_verification": self._fuyao_verification,
            "wencai_ready": self.is_wencai_ready,
            "contract_verified": self.is_contract_verified,
            "wencai_capability_status": {
                "available": self.is_wencai_ready,
                "checked_at": (
                    self._wencai_checked_at.isoformat()
                    if self._wencai_checked_at is not None
                    else None
                ),
                "last_error_code": self._wencai_last_error_code,
            },
            "live_readiness_issues": self.live_readiness_issues,
            "capabilities": self.capabilities,
            "live_capability_status": {
                name: {
                    "available": self._fuyao_capabilities[name],
                    "checked_at": (
                        self._fuyao_capability_checked_at[name].isoformat()
                        if self._fuyao_capability_checked_at[name] is not None
                        else None
                    ),
                    "last_error_code": self._fuyao_capability_errors[name],
                }
                for name in self._fuyao_capabilities
            },
            "updated_at": self._updated_at.isoformat(),
        }

    async def switch_mode(
        self, target_mode: DataMode | str, expected_revision: int
    ) -> dict[str, Any]:
        """Switch data mode with concurrency revision check.

        Raises:
            ModeRevisionConflictError: If expected_revision != self._revision.
            LiveProviderUnavailableError: If target_mode is LIVE but credentials are unconfigured.
        """
        async with self._lock:
            if expected_revision != self._revision:
                raise ModeRevisionConflictError(
                    f"Revision conflict: expected revision {expected_revision}, "
                    f"but current revision is {self._revision}."
                )

            if isinstance(target_mode, str):
                try:
                    target_enum = DataMode(target_mode.upper())
                except ValueError:
                    raise ValueError(f"Invalid data mode: {target_mode}. Must be MOCK or LIVE.")
            else:
                target_enum = target_mode

            if target_enum == DataMode.LIVE and not self.is_live_ready:
                raise LiveProviderUnavailableError(
                    "No verified external data capability is available. Configure a valid "
                    "HITHINK_FINANCE_API_KEY or a verified Wencai SkillHub provider."
                )

            if target_enum != self._mode:
                self._mode = target_enum
                self._revision += 1
                self._updated_at = datetime.now(UTC)
                logger.info(
                    "Runtime mode transitioned to %s (revision: %d)",
                    self._mode.value,
                    self._revision,
                )

            return self.get_status()


_GLOBAL_CONTROLLER: RuntimeModeController | None = None


def get_runtime_mode_controller() -> RuntimeModeController:
    """Obtain or initialize the process-level RuntimeModeController singleton."""
    global _GLOBAL_CONTROLLER
    if _GLOBAL_CONTROLLER is None:
        _GLOBAL_CONTROLLER = RuntimeModeController()
    return _GLOBAL_CONTROLLER


def reset_runtime_mode_controller(mode: DataMode | None = None) -> RuntimeModeController:
    """Reset controller singleton for test isolation."""
    global _GLOBAL_CONTROLLER
    _GLOBAL_CONTROLLER = RuntimeModeController(initial_mode=mode)
    return _GLOBAL_CONTROLLER
