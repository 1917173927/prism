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
        # If explicitly specified, use it. Otherwise, default to LIVE only if
        # WENCAI_SKILLHUB_API_KEY is present and non-empty; else default to MOCK.
        if initial_mode is not None:
            self._mode = initial_mode
        else:
            has_credentials = bool(os.getenv("WENCAI_SKILLHUB_API_KEY", "").strip())
            self._mode = DataMode.LIVE if has_credentials else DataMode.MOCK

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
        """Indicate whether official SkillHub credentials are configured."""
        return bool(os.getenv("WENCAI_SKILLHUB_API_KEY", "").strip())

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
                "stock_quote": False,  # Pending official exchange quote protocol
                "fund_lookthrough": False,  # Pending official fund disclosure protocol
                "convertible_bond": False,  # Not supported in Live yet (returns 501)
                "semantic_search": live_wencai_ready,
                "portfolio_health_check": False,
                "portfolio_rebalancing": False,
            },
        }

    def get_status(self) -> dict[str, Any]:
        """Return serialized state representation."""
        return {
            "data_mode": self._mode.value,
            "revision": self._revision,
            "live_ready": self.is_live_ready,
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
                    "Official SkillHub credentials (WENCAI_SKILLHUB_API_KEY) are missing or unconfigured. "
                    "Cannot switch to LIVE mode."
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
