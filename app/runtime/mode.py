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

        # Boot mode detection:
        # LIVE requires both server credentials and an explicit confirmation that
        # the upstream response contract has been verified.  This prevents a
        # configured but unvalidated endpoint from being presented as live data.
        if initial_mode is not None:
            self._mode = initial_mode
        else:
            self._mode = DataMode.LIVE if self.is_live_ready else DataMode.MOCK

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
        """Indicate whether credentials and the live contract gate are ready."""
        return bool(os.getenv("WENCAI_SKILLHUB_API_KEY", "").strip()) and self.is_contract_verified

    @property
    def is_contract_verified(self) -> bool:
        """Require an explicit server-side acknowledgement of provider mapping."""
        return os.getenv("WENCAI_SKILLHUB_CONTRACT_VERIFIED", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }

    @property
    def live_readiness_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if not os.getenv("WENCAI_SKILLHUB_API_KEY", "").strip():
            issues.append("WENCAI_SKILLHUB_API_KEY")
        if not self.is_contract_verified:
            issues.append("WENCAI_SKILLHUB_CONTRACT_VERIFIED")
        return tuple(issues)

    @property
    def capabilities(self) -> dict[str, Any]:
        """Matrix of feature readiness under MOCK and LIVE modes."""
        live_wencai_ready = self.is_live_ready
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
                "stock_quote": live_wencai_ready,
                "fund_lookthrough": live_wencai_ready,
                "convertible_bond": live_wencai_ready,
                "market_data": live_wencai_ready,
                "company_data": live_wencai_ready,
                "industry_data": live_wencai_ready,
                "macro_data": live_wencai_ready,
                "fund_data": live_wencai_ready,
                "convertible_bond_data": live_wencai_ready,
                "semantic_search": live_wencai_ready,
                "portfolio_health_check": live_wencai_ready,
                "portfolio_rebalancing": False,
            },
        }

    def get_status(self) -> dict[str, Any]:
        """Return serialized state representation."""
        return {
            "data_mode": self._mode.value,
            "revision": self._revision,
            "live_ready": self.is_live_ready,
            "live_readiness_issues": self.live_readiness_issues,
            "contract_verified": self.is_contract_verified,
            "capabilities": self.capabilities,
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
                    "Official SkillHub credentials or verified response contract are missing: "
                    f"{', '.join(self.live_readiness_issues)}. Cannot switch to LIVE mode."
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
