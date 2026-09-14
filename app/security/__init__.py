"""Protected local secret persistence."""

from .store import (
    ProtectedSecretStore,
    SecretProtectionError,
    WindowsDpapiProtector,
)

__all__ = [
    "ProtectedSecretStore",
    "SecretProtectionError",
    "WindowsDpapiProtector",
]
