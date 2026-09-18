"""Optional local HTTP Basic authentication with server-owned tenant identity."""
from __future__ import annotations

import base64
import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import scrypt
from hashlib import sha256
import json
import re
from pathlib import Path
from secrets import compare_digest, token_hex, token_urlsafe

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse


def password_digest(password: str, salt: str) -> str:
    return scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


@dataclass(frozen=True)
class LocalAccount:
    username: str
    owner_id: str
    salt: str
    password_hash: str
    admin: bool = False


def load_accounts(path: str | Path) -> dict[str, LocalAccount]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("local accounts must be a list")
    accounts = {}
    for row in rows:
        account = LocalAccount(**row)
        if (not isinstance(account.username, str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,100}", account.username)
                or not isinstance(account.owner_id, str) or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,200}", account.owner_id)
                or account.username in accounts):
            raise ValueError("invalid or duplicate local account")
        if len(bytes.fromhex(account.salt)) != 16 or len(bytes.fromhex(account.password_hash)) != 64:
            raise ValueError("invalid password digest")
        if type(account.admin) is not bool:
            raise ValueError("invalid local account role")
        accounts[account.username] = account
    if not accounts:
        raise ValueError("access control requires at least one account")
    return accounts


class LocalAccessMiddleware(BaseHTTPMiddleware):
    PUBLIC_PATHS = {
        "/api/health", "/login", "/api/v1/auth/context",
        "/api/v1/auth/login", "/api/v1/auth/register",
    }

    def __init__(self, app, *, accounts, store, audit, clock=None):
        super().__init__(app)
        self.accounts = accounts
        self.store = store
        self.audit = audit
        self.clock = clock or (lambda: datetime.now(UTC))
        self.dummy_salt = token_hex(16)
        self.hash_slots = asyncio.Semaphore(4)

    def issue_session(self, account: LocalAccount) -> str:
        token = token_urlsafe(32)
        now = self.clock()
        absolute = now + timedelta(hours=24)
        self.store.create_auth_session({
            "token_hash": sha256(token.encode("utf-8")).hexdigest(),
            "username": account.username,
            "owner_id": account.owner_id,
            "issued_at": now.isoformat(),
            "last_seen_at": now.isoformat(),
            "idle_expires_at": min(now + timedelta(hours=2), absolute).isoformat(),
            "absolute_expires_at": absolute.isoformat(),
        })
        return token

    def revoke_session(self, token: str | None) -> None:
        if token:
            self.store.revoke_auth_session(
                sha256(token.encode("utf-8")).hexdigest(), self.clock().isoformat()
            )

    def revoke_owner_sessions(self, owner_id: str) -> None:
        self.store.revoke_owner_sessions(owner_id, self.clock().isoformat())

    def _stored_account(self, username: str) -> LocalAccount | None:
        row = self.store.get_local_account(username)
        if row is None:
            return self.accounts.get(username)
        return LocalAccount(
            username=row["username"], owner_id=row["owner_id"], salt=row["salt"],
            password_hash=row["password_hash"], admin=bool(row["admin"]),
        )

    async def authenticate(self, username: str, password: str) -> LocalAccount | None:
        candidate = self._stored_account(username)
        from starlette.concurrency import run_in_threadpool
        async with self.hash_slots:
            digest = await run_in_threadpool(
                password_digest, password, candidate.salt if candidate else self.dummy_salt
            )
        if candidate and compare_digest(digest, candidate.password_hash):
            return candidate
        return None

    def _session_account(self, token: str) -> LocalAccount | None:
        now = self.clock()
        row = self.store.get_auth_session(
            sha256(token.encode("utf-8")).hexdigest(),
            now.isoformat(),
            (now + timedelta(hours=2)).isoformat(),
        )
        if row is None:
            return None
        return LocalAccount(
            username=row["username"], owner_id=row["owner_id"], salt=row["salt"],
            password_hash=row["password_hash"], admin=bool(row["admin"]),
        )

    async def dispatch(self, request, call_next):
        if request.url.path == "/api/v1/auth/context":
            token = request.cookies.get("prism_local_session")
            account = self._session_account(token) if token else None
            if account is None:
                try:
                    authorization = request.headers.get("authorization", "")
                    scheme, encoded = authorization.split(" ", 1)
                    if scheme.lower() == "basic":
                        username, password = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
                        account = await self.authenticate(username, password)
                except (ValueError, UnicodeError):
                    account = None
            request.state.account = account
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            return response
        if request.url.path in self.PUBLIC_PATHS or request.url.path.startswith("/static/"):
            return await call_next(request)
        account = None
        username, password = "", ""
        session_token = request.cookies.get("prism_local_session")
        if session_token:
            account = self._session_account(session_token)
        try:
            if account is None:
                authorization = request.headers.get("authorization", "")
                if len(authorization) > 4096:
                    raise ValueError("authorization too long")
                scheme, encoded = authorization.split(" ", 1)
                if scheme.lower() == "basic":
                    username, password = base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
        except (ValueError, UnicodeError):
            pass
        if account is None:
            account = await self.authenticate(username, password)
        if account is None:
            self.audit(None, request.method, "/authentication", 401)
            if request.method in {"GET", "HEAD"} and not request.url.path.startswith("/api/"):
                return RedirectResponse("/login", status_code=303)
            return JSONResponse({"error_code":"AUTH_REQUIRED", "message":"请登录本地账户"}, status_code=401,
                                headers={"WWW-Authenticate":'Basic realm="Prism", charset="UTF-8"'})
        supplied_owner = request.headers.get("x-owner-id")
        if supplied_owner and supplied_owner != account.owner_id:
            self.audit(account.owner_id, request.method, "/owner-denied", 403)
            return JSONResponse({"error_code":"OWNER_SCOPE", "message":"账户无权访问该数据空间"}, status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if request.headers.get("sec-fetch-site") == "cross-site" or (origin and origin.rstrip("/") != str(request.base_url).rstrip("/")):
                self.audit(account.owner_id, request.method, "/origin-denied", 403)
                return JSONResponse({"error_code":"ORIGIN_DENIED"}, status_code=403)
            if request.url.path in (
                "/api/v1/runtime/data-mode",
                "/api/v1/runtime/wencai-settings",
                "/api/v1/runtime/wencai-settings/test",
            ) and not account.admin:
                self.audit(account.owner_id, request.method, "/admin-denied", 403)
                return JSONResponse({"error_code":"ADMIN_REQUIRED"}, status_code=403)
        request.state.account = account
        headers = [(k,v) for k,v in request.scope["headers"] if k.lower() != b"x-owner-id"]
        headers.append((b"x-owner-id", account.owner_id.encode("utf-8")))
        request.scope["headers"] = headers
        try:
            response = await call_next(request)
        except Exception:
            route = request.scope.get("route")
            self.audit(account.owner_id, request.method, getattr(route, "path", "/unknown"), 500)
            raise
        route = request.scope.get("route")
        self.audit(account.owner_id, request.method, getattr(route, "path", "/static"), response.status_code)
        response.headers["Cache-Control"] = "no-store"
        return response
