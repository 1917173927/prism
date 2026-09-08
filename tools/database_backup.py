"""Verified SQLite backup and restore to a new path; never overwrite an existing database."""
from __future__ import annotations

import argparse
from pathlib import Path
import sqlite3


def copy_database(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if source == destination:
        raise ValueError("source and destination must differ")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects both current data and previous backups.
    with destination.open("xb"):
        pass
    reader = writer = None
    try:
        reader = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        writer = sqlite3.connect(destination)
        reader.backup(writer)
        if writer.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("backup integrity check failed")
    except Exception:
        if writer:
            writer.close()
            writer = None
        destination.unlink(missing_ok=True)
        raise
    finally:
        if writer:
            writer.close()
        if reader:
            reader.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    copy_database(args.source, args.destination)
    print(f"{args.operation}: integrity_check=ok; destination={args.destination}")


if __name__ == "__main__":
    main()
