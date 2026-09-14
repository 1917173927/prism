"""Global test isolation for workstation runtime state."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

import pytest


# Set this before test modules import app.api.main. The desktop module-level app
# may restore a real DPAPI credential, but tests must never inherit or mutate the
# workstation's protected provider settings.
_ORIGINAL_SECRET_STORE_PATH = os.environ.get("PRISM_SECRET_STORE_PATH")
_TEST_SECRET_DIR = Path(tempfile.mkdtemp(prefix="prism-pytest-secrets-"))
os.environ["PRISM_SECRET_STORE_PATH"] = str(_TEST_SECRET_DIR / "secrets.json")

from app.runtime.mode import DataMode, reset_runtime_mode_controller


@pytest.fixture(autouse=True)
def isolate_runtime_mode():
    """Start every test from explicit MOCK unless that test opts into LIVE."""
    reset_runtime_mode_controller(DataMode.MOCK)
    yield
    reset_runtime_mode_controller(DataMode.MOCK)


def pytest_unconfigure(config):
    if _ORIGINAL_SECRET_STORE_PATH is None:
        os.environ.pop("PRISM_SECRET_STORE_PATH", None)
    else:
        os.environ["PRISM_SECRET_STORE_PATH"] = _ORIGINAL_SECRET_STORE_PATH
    shutil.rmtree(_TEST_SECRET_DIR, ignore_errors=True)
