"""Exact A-share identity lookup through the official exchange directories.

This provider deliberately resolves only a security name and exchange code.  It
does not supply prices, fundamentals, sectors, or any other market fact.  Both
upstreams are public exchange directories and require no distributable API key.
"""

from __future__ import annotations

import asyncio
from html import unescape
import re
from time import monotonic
from typing import Any

import httpx


class SecurityDirectoryError(RuntimeError):
    """Raised when an official directory cannot be read safely."""


class OfficialSecurityDirectoryProvider:
    """Resolve one exact A-share display name without a private credential."""

    SSE_DIRECTORY_URL = "https://www.sse.com.cn/js/common/ssesuggestdata.js"
    SZSE_DIRECTORY_URL = "https://www.szse.cn/api/report/ShowReport/data"
    _SSE_ROW = re.compile(
        r'_t\.push\(\{val:"(?P<code>\d{6})",val2:"(?P<name>[^"]+)"',
    )
    _SSE_CODE = re.compile(r"(?:600|601|603|605|688|689)\d{3}")
    _SZSE_CODE = re.compile(r"(?:000|001|002|003|300|301)\d{3}")
    _TAG = re.compile(r"<[^>]+>")

    def __init__(
        self,
        *,
        timeout_seconds: float = 3.0,
        cache_ttl_seconds: float = 6 * 60 * 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._cache_ttl_seconds = cache_ttl_seconds
        self._transport = transport
        self._sse_by_name: dict[str, tuple[str, ...]] = {}
        self._sse_loaded_at = 0.0
        self._sse_failed_at = 0.0
        self._sse_lock = asyncio.Lock()
        self._resolved_cache: dict[str, tuple[float, dict[str, str] | None]] = {}

    @staticmethod
    def _normalized_name(value: object) -> str:
        return re.sub(r"\s+", "", unescape(str(value or ""))).strip()

    async def _request(self, url: str, *, params: dict[str, str] | None = None) -> httpx.Response:
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                follow_redirects=False,
                transport=self._transport,
                headers={
                    "Accept": "application/json,text/javascript,text/plain,*/*",
                    "User-Agent": "Prism/0.1 official-security-directory",
                },
            ) as client:
                response = await client.get(url, params=params)
            response.raise_for_status()
            return response
        except (httpx.HTTPError, TimeoutError) as exc:
            raise SecurityDirectoryError("official security directory is unavailable") from exc

    async def _load_sse_directory(self) -> dict[str, tuple[str, ...]]:
        now = monotonic()
        if self._sse_by_name and now - self._sse_loaded_at <= self._cache_ttl_seconds:
            return self._sse_by_name
        if self._sse_failed_at and now - self._sse_failed_at <= 60:
            raise SecurityDirectoryError("official SSE directory is temporarily unavailable")
        async with self._sse_lock:
            now = monotonic()
            if self._sse_by_name and now - self._sse_loaded_at <= self._cache_ttl_seconds:
                return self._sse_by_name
            if self._sse_failed_at and now - self._sse_failed_at <= 60:
                raise SecurityDirectoryError("official SSE directory is temporarily unavailable")
            try:
                response = await self._request(self.SSE_DIRECTORY_URL)
            except SecurityDirectoryError:
                self._sse_failed_at = monotonic()
                raise
            matches: dict[str, list[str]] = {}
            for row in self._SSE_ROW.finditer(response.text):
                code = row.group("code")
                name = self._normalized_name(row.group("name"))
                if name and self._SSE_CODE.fullmatch(code):
                    matches.setdefault(name, []).append(code)
            if not matches:
                self._sse_failed_at = monotonic()
                raise SecurityDirectoryError("official SSE directory returned no A-share identities")
            self._sse_by_name = {
                name: tuple(dict.fromkeys(codes)) for name, codes in matches.items()
            }
            self._sse_loaded_at = monotonic()
            self._sse_failed_at = 0.0
            return self._sse_by_name

    async def _resolve_sse(self, name: str) -> dict[str, str] | None:
        codes = (await self._load_sse_directory()).get(name, ())
        if len(codes) != 1:
            return None
        return {
            "asset_id": f"{codes[0]}.SH",
            "name": name,
            "market": "SH",
            "source": "Shanghai Stock Exchange security directory",
        }

    async def _resolve_szse(self, name: str) -> dict[str, str] | None:
        response = await self._request(
            self.SZSE_DIRECTORY_URL,
            params={
                "SHOWTYPE": "JSON",
                "CATALOGID": "1110",
                "TABKEY": "tab1",
                "PAGENO": "1",
                "txtDMorJC": name,
            },
        )
        try:
            payload: Any = response.json()
        except ValueError as exc:
            raise SecurityDirectoryError("official SZSE directory returned invalid JSON") from exc
        if not isinstance(payload, list):
            raise SecurityDirectoryError("official SZSE directory returned an invalid contract")
        exact: dict[str, dict[str, str]] = {}
        for section in payload:
            if not isinstance(section, dict):
                continue
            for row in section.get("data") or ():
                if not isinstance(row, dict):
                    continue
                code = str(row.get("agdm") or "").strip()
                display_name = self._normalized_name(self._TAG.sub("", str(row.get("agjc") or "")))
                if display_name != name or self._SZSE_CODE.fullmatch(code) is None:
                    continue
                exact[code] = {
                    "asset_id": f"{code}.SZ",
                    "name": display_name,
                    "market": "SZ",
                    "source": "Shenzhen Stock Exchange A-share directory",
                }
        return next(iter(exact.values())) if len(exact) == 1 else None

    async def resolve_security_identity(self, display_name: str) -> dict[str, str] | None:
        """Return one identity only when an official directory has an exact match."""
        name = self._normalized_name(display_name)
        if not name or len(name) > 80:
            return None
        cached = self._resolved_cache.get(name)
        now = monotonic()
        if cached is not None and now - cached[0] <= self._cache_ttl_seconds:
            return dict(cached[1]) if cached[1] is not None else None

        results = await asyncio.gather(
            self._resolve_sse(name),
            self._resolve_szse(name),
            return_exceptions=True,
        )
        identities = {
            item["asset_id"]: item
            for item in results
            if isinstance(item, dict) and item.get("asset_id")
        }
        identity = next(iter(identities.values())) if len(identities) == 1 else None
        # Cache only a conclusive exact match.  A temporary failure must not
        # become a long-lived negative result.
        if identity is not None:
            self._resolved_cache[name] = (now, dict(identity))
            return dict(identity)
        if all(not isinstance(item, Exception) for item in results):
            self._resolved_cache[name] = (now, None)
        return None


__all__ = ["OfficialSecurityDirectoryProvider", "SecurityDirectoryError"]
