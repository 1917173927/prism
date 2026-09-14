import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.security import ProtectedSecretStore, SecretProtectionError


class ReversibleTestProtector:
    def protect(self, plaintext: bytes) -> bytes:
        return b"protected:" + plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        if not ciphertext.startswith(b"protected:"):
            raise SecretProtectionError("invalid test ciphertext")
        return ciphertext.removeprefix(b"protected:")[::-1]


def test_secret_store_round_trip_never_writes_plaintext(tmp_path) -> None:
    path = tmp_path / "secrets.json"
    store = ProtectedSecretStore(path, ReversibleTestProtector())

    store.set("llm:owner-a", "highly-sensitive-value")

    assert store.get("llm:owner-a") == "highly-sensitive-value"
    assert "highly-sensitive-value" not in path.read_text(encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == "prism-protected-secrets.v1"


def test_secret_store_delete_is_scoped_and_persistent(tmp_path) -> None:
    path = tmp_path / "secrets.json"
    store = ProtectedSecretStore(path, ReversibleTestProtector())
    store.set("llm:owner-a", "a")
    store.set("llm:owner-b", "b")

    assert store.delete("llm:owner-a") is True
    assert store.delete("llm:owner-a") is False
    assert store.get("llm:owner-a") is None
    assert ProtectedSecretStore(path, ReversibleTestProtector()).get("llm:owner-b") == "b"


def test_secret_store_rejects_invalid_key_and_corrupt_file(tmp_path) -> None:
    path = tmp_path / "secrets.json"
    store = ProtectedSecretStore(path, ReversibleTestProtector())
    with pytest.raises(ValueError):
        store.set("../escape", "secret")

    path.write_text('{"schema_version":"wrong","entries":{}}', encoding="utf-8")
    with pytest.raises(SecretProtectionError):
        store.get("llm:owner-a")


def test_two_store_instances_do_not_lose_concurrent_owner_updates(tmp_path) -> None:
    path = tmp_path / "secrets.json"
    first = ProtectedSecretStore(path, ReversibleTestProtector())
    second = ProtectedSecretStore(path, ReversibleTestProtector())

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda item: item[0].set(item[1], item[2]), (
            (first, "llm:owner-a", "a"),
            (second, "llm:owner-b", "b"),
        )))

    assert first.get("llm:owner-a") == "a"
    assert second.get("llm:owner-b") == "b"
