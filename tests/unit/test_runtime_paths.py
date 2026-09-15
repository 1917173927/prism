from __future__ import annotations

from pathlib import Path

from app.runtime.paths import default_private_data_dir


def test_linked_worktree_uses_existing_common_private_data_dir(tmp_path: Path) -> None:
    main_root = tmp_path / "main"
    worktree_root = tmp_path / "worktree"
    (main_root / ".git" / "worktrees" / "repair").mkdir(parents=True)
    (main_root / "data" / "private").mkdir(parents=True)
    worktree_root.mkdir()
    (worktree_root / ".git").write_text(
        "gitdir: ../main/.git/worktrees/repair\n", encoding="utf-8"
    )

    assert default_private_data_dir(worktree_root) == main_root / "data" / "private"


def test_regular_checkout_keeps_private_data_local(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".git").mkdir(parents=True)

    assert default_private_data_dir(repo_root) == repo_root / "data" / "private"
