"""Manage the private Windows PostgreSQL cluster without exposing passwords."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from app.security.store import ProtectedSecretStore

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "data" / "private" / "postgresql"
BIN = PRIVATE / "runtime" / "pgsql" / "bin"
CLUSTER = PRIVATE / "cluster"
PORT = 55432


def credentials():
    return ProtectedSecretStore(PRIVATE / "connection-secrets.json")


def run_binary(name, *arguments, check=True):
    executable = BIN / (name + ".exe")
    if not executable.is_file():
        raise RuntimeError("Official PostgreSQL binaries are not installed in the private runtime directory")
    # The server launched by pg_ctl can inherit output handles. Pipes would
    # keep communicate() waiting after pg_ctl exits; server logs have a file.
    result = subprocess.run([str(executable), *map(str, arguments)], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0, timeout=60)
    if check and result.returncode:
        raise RuntimeError(f"PostgreSQL {name} failed; inspect the private cluster log")
    return result


def dsn(kind="test"):
    from psycopg.conninfo import make_conninfo
    password = credentials().get("postgres." + kind)
    if not password:
        raise RuntimeError("Local PostgreSQL credentials have not been initialized")
    names = {"admin": ("prism_admin", "postgres"), "test": ("prism_test", "prism_test"),
             "app": ("prism_app", "prism_app")}
    username, database = names[kind]
    return make_conninfo(host="127.0.0.1", port=PORT, user=username, dbname=database,
                         password=password, connect_timeout=5)


def start():
    if run_binary("pg_ctl", "-D", CLUSTER, "status", check=False).returncode:
        run_binary("pg_ctl", "-D", CLUSTER, "-l", PRIVATE / "server.log", "-w", "-t", "30",
                   "-o", f"-h 127.0.0.1 -p {PORT}", "start")


def initialize():
    from psycopg import connect, sql
    PRIVATE.mkdir(parents=True, exist_ok=True)
    secret_store = credentials()
    if not (CLUSTER / "PG_VERSION").exists():
        password = secret_store.get("postgres.admin") or secrets.token_urlsafe(36)
        secret_store.set("postgres.admin", password)
        # initdb requires a password file; it is short lived and stays private.
        password_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=PRIVATE, suffix=".pw", delete=False) as handle:
                password_path = Path(handle.name)
                handle.write((password + "\n").encode("utf-8"))
            run_binary("initdb", "-D", CLUSTER, "-U", "prism_admin", "--encoding=UTF8",
                       "--locale=C", "--auth=scram-sha-256", "--pwfile=" + str(password_path))
        finally:
            if password_path is not None:
                password_path.unlink(missing_ok=True)
    start()
    with connect(dsn("admin"), autocommit=True) as connection:
        for kind in ("test", "app"):
            name = "prism_" + kind
            exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,)).fetchone()
            if not exists:
                password = secret_store.get("postgres." + kind) or secrets.token_urlsafe(36)
                secret_store.set("postgres." + kind, password)
                connection.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {}").format(
                    sql.Identifier(name), sql.Literal(password)))
            elif not secret_store.get("postgres." + kind):
                raise RuntimeError("Existing local role has no protected credential; no password was changed")
            if not connection.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
                connection.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(name), sql.Identifier(name)))


def status():
    from psycopg import connect
    with connect(dsn("test")) as connection:
        version = connection.execute("SELECT version()").fetchone()[0]
        address, port = connection.execute("SELECT inet_server_addr(),inet_server_port()").fetchone()
    return {"status": "READY", "version": version, "host": str(address), "port": port,
            "database": "prism_test", "application_database": "prism_app",
            "credential_storage": "WINDOWS_CURRENT_USER_DPAPI", "business_sqlite_changed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "start", "stop", "status", "test", "serve"))
    parser.add_argument("--full", action="store_true", help="Run full pytest with the dedicated test DSN")
    parser.add_argument("--port", type=int, default=8001, help="Optional application HTTP port")
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This helper uses the local Windows binary installation and DPAPI")
    try:
        if args.action == "init":
            initialize()
        elif args.action == "start":
            start()
        elif args.action == "stop":
            run_binary("pg_ctl", "-D", CLUSTER, "-m", "fast", "-w", "stop")
            print('{"status":"STOPPED"}')
            return
        elif args.action in {"test", "serve"}:
            start()
            environment = dict(os.environ)
            if args.action == "test":
                environment.pop("PRISM_DATABASE_URL", None)
                environment["PRISM_TEST_POSTGRES_DSN"] = dsn("test")
                command = [sys.executable, "-m", "pytest", "--tb=short"]
                if not args.full:
                    command += ["tests/integration/test_postgres_store.py", "tests/integration/test_research_postgres.py"]
            else:
                environment["PRISM_DATABASE_URL"] = dsn("app")
                command = [sys.executable, "-m", "uvicorn", "app.api.main:app", "--host", "127.0.0.1", "--port", str(args.port), "--workers", "1"]
            raise SystemExit(subprocess.call(command, cwd=ROOT, env=environment))
        print(json.dumps(status(), ensure_ascii=False))
    except Exception as error:
        # Driver diagnostics can contain DSNs; never echo them or passwords.
        print(json.dumps({"status": "FAILED", "error_type": type(error).__name__,
                          "message": "Local PostgreSQL operation failed; credentials were not displayed"}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
