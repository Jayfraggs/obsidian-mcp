from pathlib import Path

import pytest

from obsidian_mcp.errors import ErrorCode, VaultPathError
from obsidian_mcp.vault.paths import VaultPathResolver


def test_resolve_note_path_adds_markdown_suffix(tmp_path: Path) -> None:
    resolver = VaultPathResolver(tmp_path)

    assert resolver.resolve_note_path("Daily/Today") == tmp_path / "Daily" / "Today.md"


def test_resolve_note_path_keeps_existing_markdown_suffix(tmp_path: Path) -> None:
    resolver = VaultPathResolver(tmp_path)

    assert resolver.resolve_note_path("Daily/Today.md") == tmp_path / "Daily" / "Today.md"


@pytest.mark.parametrize("bad", [
    "C:/outside.md",            # Windows drive path — is_absolute() is False for this on Linux/macOS
    "C:\\outside.md",
    "\\\\server\\share\\note.md",   # UNC
    "/etc/passwd",              # POSIX absolute
])
def test_resolve_relative_path_rejects_absolute_paths(tmp_path: Path, bad: str) -> None:
    resolver = VaultPathResolver(tmp_path)

    with pytest.raises(VaultPathError) as exc_info:
        resolver.resolve_relative_path(bad)

    assert exc_info.value.code is ErrorCode.VAULT_PATH_INVALID


def test_resolve_relative_path_still_accepts_normal_relative_paths(tmp_path: Path) -> None:
    resolver = VaultPathResolver(tmp_path)

    assert resolver.resolve_relative_path("Notes/Today.md") == tmp_path.resolve() / "Notes" / "Today.md"
    assert resolver.resolve_relative_path(Path("a") / "b.md") == tmp_path.resolve() / "a" / "b.md"


def test_resolve_relative_path_rejects_parent_traversal(tmp_path: Path) -> None:
    resolver = VaultPathResolver(tmp_path)

    with pytest.raises(VaultPathError):
        resolver.resolve_relative_path("../outside.md")


def test_resolve_relative_path_rejects_empty_path(tmp_path: Path) -> None:
    resolver = VaultPathResolver(tmp_path)

    with pytest.raises(VaultPathError):
        resolver.resolve_relative_path("")
