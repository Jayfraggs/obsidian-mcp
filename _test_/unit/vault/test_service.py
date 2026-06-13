from pathlib import Path

import pytest

from obsidian_mcp.errors import NoteAlreadyExistsError, NoteNotFoundError
from obsidian_mcp.vault.service import VaultService


def test_create_and_read_note_returns_metadata(tmp_path: Path) -> None:
    service = VaultService(tmp_path)

    created = service.create_note("Projects/Home", "---\naliases: [Hub]\n---\n# Home\n#tag")
    read = service.read_note("Projects/Home")

    assert created["path"] == "Projects/Home.md"
    assert read["content"].endswith("# Home\n#tag")
    assert read["metadata"]["aliases"] == ["Hub"]
    assert read["metadata"]["tags"] == ["tag"]


def test_create_note_rejects_existing_note(tmp_path: Path) -> None:
    service = VaultService(tmp_path)
    service.create_note("Note", "first")

    with pytest.raises(NoteAlreadyExistsError):
        service.create_note("Note.md", "second")


def test_update_append_and_delete_note(tmp_path: Path) -> None:
    service = VaultService(tmp_path)
    service.create_note("Note", "first")

    service.update_note("Note", "second")
    service.append_note("Note", "third")
    read = service.read_note("Note")

    assert read["content"] == "second\nthird"

    deleted = service.delete_note("Note")

    assert deleted == {"path": "Note.md", "deleted": True}
    with pytest.raises(NoteNotFoundError):
        service.read_note("Note")


def test_move_and_rename_note(tmp_path: Path) -> None:
    service = VaultService(tmp_path)
    service.create_note("Inbox/Idea", "content")

    moved = service.move_note("Inbox/Idea", "Archive/Idea")
    renamed = service.rename_note("Archive/Idea", "Better Idea")

    assert moved == {"from": "Inbox/Idea.md", "to": "Archive/Idea.md"}
    assert renamed == {"from": "Archive/Idea.md", "to": "Archive/Better Idea.md"}
    assert service.read_note("Archive/Better Idea")["content"] == "content"


def test_list_files_and_folders_are_sorted(tmp_path: Path) -> None:
    service = VaultService(tmp_path)
    service.create_note("Zeta/Two", "content")
    service.create_note("Alpha/One", "content")
    (tmp_path / "Alpha" / "asset.png").write_text("asset", encoding="utf-8")

    assert service.list_files() == ["Alpha/One.md", "Alpha/asset.png", "Zeta/Two.md"]
    assert service.list_folders() == ["Alpha", "Zeta"]


def test_search_notes_returns_ranked_bounded_results(tmp_path: Path) -> None:
    service = VaultService(tmp_path)
    service.create_note("One", "alpha project planning")
    service.create_note("Two", "beta project planning")
    service.create_note("Three", "unrelated")

    results = service.search_notes("project", limit=2)

    assert [result["path"] for result in results] == ["One.md", "Two.md"]
    assert all(result["score"] > 0 for result in results)
    assert all("project" in result["preview"] for result in results)


def test_backlinks_include_notes_linking_to_target(tmp_path: Path) -> None:
    service = VaultService(tmp_path)
    service.create_note("Target", "target")
    service.create_note("Source", "Links to [[Target]]")
    service.create_note("Other", "Links to [[Elsewhere]]")

    read = service.read_note("Target")

    assert read["backlinks"] == ["Source.md"]
