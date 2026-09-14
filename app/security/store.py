"""Small protected secret store for the local desktop deployment.

The JSON file contains only DPAPI-protected blobs.  Plaintext credentials never
leave process memory and are never written to the application database.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
from threading import RLock
import tempfile
from typing import Protocol


class SecretProtectionError(RuntimeError):
    """Raised when protected storage cannot be read or written safely."""


class SecretProtector(Protocol):
    def protect(self, plaintext: bytes) -> bytes: ...
    def unprotect(self, ciphertext: bytes) -> bytes: ...


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class WindowsDpapiProtector:
    """Protect secrets for the Windows account running Prism."""

    _DESCRIPTION = "Prism protected local credential"
    _FLAGS = 0x1  # CRYPTPROTECT_UI_FORBIDDEN

    def __init__(self) -> None:
        if os.name != "nt":
            raise SecretProtectionError("Windows DPAPI is unavailable on this platform")
        self._crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        blob_pointer = ctypes.POINTER(_DataBlob)
        self._crypt32.CryptProtectData.argtypes = [
            blob_pointer, wintypes.LPCWSTR, blob_pointer, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD, blob_pointer,
        ]
        self._crypt32.CryptProtectData.restype = wintypes.BOOL
        self._crypt32.CryptUnprotectData.argtypes = [
            blob_pointer, ctypes.c_void_p, blob_pointer, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD, blob_pointer,
        ]
        self._crypt32.CryptUnprotectData.restype = wintypes.BOOL
        self._kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        self._kernel32.LocalFree.restype = ctypes.c_void_p

    @staticmethod
    def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
        buffer = ctypes.create_string_buffer(data)
        blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        return blob, buffer

    def protect(self, plaintext: bytes) -> bytes:
        source, source_buffer = self._blob(plaintext)
        output = _DataBlob()
        try:
            if not self._crypt32.CryptProtectData(
                ctypes.byref(source),
                self._DESCRIPTION,
                None,
                None,
                None,
                self._FLAGS,
                ctypes.byref(output),
            ):
                raise SecretProtectionError("Windows could not protect the credential")
            try:
                return ctypes.string_at(output.pbData, output.cbData)
            finally:
                if output.pbData:
                    ctypes.memset(output.pbData, 0, output.cbData)
                    self._kernel32.LocalFree(output.pbData)
        finally:
            ctypes.memset(ctypes.addressof(source_buffer), 0, ctypes.sizeof(source_buffer))

    def unprotect(self, ciphertext: bytes) -> bytes:
        source, source_buffer = self._blob(ciphertext)
        output = _DataBlob()
        try:
            if not self._crypt32.CryptUnprotectData(
                ctypes.byref(source), None, None, None, None, self._FLAGS, ctypes.byref(output)
            ):
                raise SecretProtectionError("Windows could not unlock the credential")
            try:
                return ctypes.string_at(output.pbData, output.cbData)
            finally:
                if output.pbData:
                    ctypes.memset(output.pbData, 0, output.cbData)
                    self._kernel32.LocalFree(output.pbData)
        finally:
            ctypes.memset(ctypes.addressof(source_buffer), 0, ctypes.sizeof(source_buffer))


class ProtectedSecretStore:
    """Atomic JSON registry whose values are protected by an injected protector."""

    _KEY = re.compile(r"^[A-Za-z0-9_.:@-]{1,300}$")

    def __init__(self, path: str | Path, protector: SecretProtector | None = None) -> None:
        self.path = Path(path)
        self._protector = protector or WindowsDpapiProtector()
        self._lock = RLock()

    @classmethod
    def _validate_key(cls, key: str) -> str:
        if not isinstance(key, str) or cls._KEY.fullmatch(key) is None:
            raise ValueError("invalid protected secret key")
        return key

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise SecretProtectionError("protected secret store is unreadable") from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != "prism-protected-secrets.v1"
            or not isinstance(payload.get("entries"), dict)
            or not all(isinstance(key, str) and isinstance(value, str) for key, value in payload["entries"].items())
        ):
            raise SecretProtectionError("protected secret store has an invalid format")
        return payload["entries"]

    def _write(self, entries: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {"schema_version": "prism-protected-secrets.v1", "entries": entries}
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=self.path.name + ".", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                json.dump(document, handle, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            try:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise SecretProtectionError("protected secret store could not be written") from exc

    @contextmanager
    def _process_lock(self):
        """Serialize read-modify-replace across processes using a sidecar lock."""
        handle = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock_path = self.path.with_suffix(self.path.suffix + ".lock")
            handle = lock_path.open("a+b")
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            raise SecretProtectionError("protected secret store lock is unavailable") from exc
        finally:
            if handle is not None:
                handle.close()

    def get(self, key: str) -> str | None:
        key = self._validate_key(key)
        with self._lock:
            with self._process_lock():
                encoded = self._read().get(key)
            if encoded is None:
                return None
            try:
                ciphertext = base64.b64decode(encoded, validate=True)
                return self._protector.unprotect(ciphertext).decode("utf-8")
            except (ValueError, UnicodeError, SecretProtectionError) as exc:
                raise SecretProtectionError("protected credential could not be decoded") from exc

    def set(self, key: str, value: str) -> None:
        key = self._validate_key(key)
        if not isinstance(value, str) or not value:
            raise ValueError("protected secret value must not be empty")
        with self._lock:
            with self._process_lock():
                entries = self._read()
                ciphertext = self._protector.protect(value.encode("utf-8"))
                entries[key] = base64.b64encode(ciphertext).decode("ascii")
                self._write(entries)

    def delete(self, key: str) -> bool:
        key = self._validate_key(key)
        with self._lock:
            with self._process_lock():
                entries = self._read()
                if key not in entries:
                    return False
                del entries[key]
                self._write(entries)
                return True
