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


def test_resolve_relative_path_rejects_absolute_paths(tmp_path: Path) -> None:
    resolver = VaultPathResolver(tmp_path)

    with pytest.raises(VaultPathError) as exc_info:
        resolver.resolve_relative_path(Path("C:/outside.md"))

    assert exc_info.value.code is ErrorCode.VAULT_PATH_INVALID


def test_resolve_relative_path_rejects_parent_traversal(tmp_path: Path) -> None:
    resolver = VaultPathResolver(tmp_path)

    with pytest.raises(VaultPathError):
        resolver.resolve_relative_path("../outside.md")


def test_resolve_relative_path_rejects_empty_path(tmp_path: Path) -> None:
    resolver = VaultPathResolver(tmp_path)

    with pytest.raises(VaultPathError):
        resolver.resolve_relative_path("")
