import sqlite3

import pytest

from tools.database_backup import copy_database


def test_online_backup_restore_preserves_committed_data_and_never_overwrites(tmp_path):
    source = tmp_path / "source.sqlite3"
    backup = tmp_path / "backup.sqlite3"
    restored = tmp_path / "restored.sqlite3"
    connection = sqlite3.connect(source)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE holdings(owner TEXT, amount INTEGER)")
        connection.execute("INSERT INTO holdings VALUES ('a', 123)")
        connection.commit()
        copy_database(source, backup)
        copy_database(backup, restored)
        with sqlite3.connect(restored) as check:
            assert check.execute("SELECT * FROM holdings").fetchall() == [("a", 123)]
        with pytest.raises(FileExistsError):
            copy_database(backup, source)
        assert connection.execute("SELECT amount FROM holdings").fetchone() == (123,)
    finally:
        connection.close()
