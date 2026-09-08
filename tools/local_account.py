"""Create a local account without putting plaintext passwords in command arguments."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from getpass import getpass
import json
from pathlib import Path
from secrets import token_hex
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.api.access import LocalAccount, load_accounts, password_digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=Path("data/private/accounts.json"))
    parser.add_argument("--username", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--admin", action="store_true")
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    accounts = load_accounts(args.file) if args.file.exists() else {}
    if args.username in accounts and not args.replace:
        parser.error("account exists; use --replace to rotate its password")
    password = getpass("Password (at least 12 characters): ")
    if len(password) < 12 or len(password) > 512 or password != getpass("Confirm password: "):
        parser.error("password length or confirmation is invalid")
    salt = token_hex(16)
    accounts[args.username] = LocalAccount(args.username, args.owner, salt, password_digest(password, salt), args.admin)
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
