"""Resolve local application data consistently across Git worktrees."""

from __future__ import annotations

from pathlib import Path


def _common_repository_root(repo_root: Path) -> Path:
    """Return the main checkout root when *repo_root* is a linked worktree."""
    git_marker = repo_root / ".git"
    if git_marker.is_dir():
        return repo_root
    if not git_marker.is_file():
        return repo_root
    try:
        first_line = git_marker.read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, UnicodeError, IndexError):
        return repo_root
    prefix = "gitdir:"
    if not first_line.lower().startswith(prefix):
        return repo_root
    git_dir = Path(first_line[len(prefix):].strip())
    if not git_dir.is_absolute():
        git_dir = (repo_root / git_dir).resolve()
    else:
        git_dir = git_dir.resolve()
    common_git = git_dir.parent.parent
    if common_git.name != ".git":
        return repo_root
    common_root = common_git.parent
    return common_root if (common_root / ".git").exists() else repo_root


def default_private_data_dir(repo_root: Path | None = None) -> Path:
    """Return the shared local data directory, preserving explicit overrides.

    A linked worktree contains code and tests but normally does not contain the
    ignored ``data/private`` files from the main checkout.  Resolve that one
    shared application-data location from Git metadata so a worktree uses the
    same protected credentials and confirmed portfolio by default.  Callers
    may still override individual files with their existing environment vars.
    """
    root = (repo_root or Path(__file__).resolve().parents[2]).resolve()
    common_root = _common_repository_root(root)
    common_private = common_root / "data" / "private"
    if common_root != root and common_private.exists():
        return common_private
    return root / "data" / "private"


__all__ = ["default_private_data_dir"]
