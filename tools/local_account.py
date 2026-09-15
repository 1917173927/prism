"""Create a local account without putting plaintext passwords in command arguments."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from getpass import getpass
import json
import os
from pathlib import Path
from secrets import token_hex
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api.access import LocalAccount, load_accounts, password_digest
from app.store import SQLiteDecisionEventStore


def default_database_path() -> Path:
    return Path(os.getenv("PRISM_DB_PATH") or "data/private/prism.sqlite3")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--file", type=Path, help="legacy JSON account file")
    parser.add_argument("--username", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--admin", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    accounts = load_accounts(args.file) if args.file and args.file.exists() else {}
    if args.file and args.username in accounts and not args.replace:
        parser.error("account exists; use --replace to rotate its password")
    password = getpass("Password (at least 12 characters): ")
    if len(password) < 12 or len(password) > 512 or password != getpass("Confirm password: "):
        parser.error("password length or confirmation is invalid")
    salt = token_hex(16)
    account = LocalAccount(args.username, args.owner, salt, password_digest(password, salt), args.admin)
    if not args.file:
        from datetime import UTC, datetime
        database_url = os.getenv("PRISM_DATABASE_URL", "").strip()
        if database_url and args.database is not None:
            parser.error("--database cannot be combined with PRISM_DATABASE_URL")
        if database_url:
            from app.store.postgres import PostgresDecisionEventStore
            store = PostgresDecisionEventStore(database_url)
        else:
            database_path = args.database or default_database_path()
            database_path.parent.mkdir(parents=True, exist_ok=True)
            store = SQLiteDecisionEventStore(database_path)
        existing = store.get_local_account(args.username)
        if existing and not args.replace:
            store.close()
            parser.error("account exists; use --replace to rotate its password")
        if existing:
            if existing["owner_id"] != args.owner or bool(existing["admin"]) != args.admin:
                store.close()
                parser.error("--replace rotates only the password; owner and role must match")
            store.change_local_password(args.username, account.salt, account.password_hash, datetime.now(UTC).isoformat())
            store.revoke_owner_sessions(args.owner, datetime.now(UTC).isoformat())
        else:
            now = datetime.now(UTC).isoformat()
            store.create_local_account({**asdict(account), "created_at": now, "updated_at": now})
        store.close()
        print("Local account database updated. Existing sessions were revoked after password rotation.")
        return
    accounts[args.username] = account
    args.file.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.file.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump([asdict(account) for account in accounts.values()], handle, ensure_ascii=False, indent=2)
        load_accounts(temporary)
        temporary.replace(args.file)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    print("Local account saved. Password is stored only as a salted scrypt digest.")


if __name__ == "__main__":
    main()
