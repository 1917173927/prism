"""Optional local HTTP Basic authentication with server-owned tenant identity."""
from __future__ import annotations

import base64
import asyncio
from dataclasses import dataclass
from hashlib import scrypt
import json
import re
from pathlib import Path
from secrets import compare_digest, token_hex, token_urlsafe

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


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
    def __init__(self, app, *, accounts, audit):
        super().__init__(app)
        self.accounts = accounts
        self.audit = audit
        self.dummy_salt = token_hex(16)
        self.hash_slots = asyncio.Semaphore(4)
        self.sessions: dict[str, LocalAccount] = {}

    def issue_session(self, account: LocalAccount) -> str:
        token = token_urlsafe(32)
        self.sessions[token] = account
        return token

    def revoke_session(self, token: str | None) -> None:
        if token:
            self.sessions.pop(token, None)

    async def dispatch(self, request, call_next):
        if request.url.path in {"/api/health", "/login"}:
            return await call_next(request)
        account = None
        username, password = "", ""
        session_token = request.cookies.get("prism_local_session")
        if session_token:
            account = self.sessions.get(session_token)
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
        candidate = self.accounts.get(username)
        # Keep CPU-heavy password derivation off the async event loop.
        from starlette.concurrency import run_in_threadpool
        if account is None:
            async with self.hash_slots:
                digest = await run_in_threadpool(password_digest, password, candidate.salt if candidate else self.dummy_salt)
            if candidate and compare_digest(digest, candidate.password_hash):
                account = candidate
        if account is None:
            self.audit(None, request.method, "/authentication", 401)
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
            if request.url.path in ("/api/v1/copilot/config", "/api/v1/runtime/data-mode") and not account.admin:
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
