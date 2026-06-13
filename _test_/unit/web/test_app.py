from pathlib import Path

from fastapi.testclient import TestClient

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.permissions import PermissionProfile
from obsidian_mcp.web.app import create_web_app


def test_status_and_permission_profile_routes(tmp_path: Path) -> None:
    settings = ObsidianMCPSettings(vault_path=tmp_path)
    client = TestClient(create_web_app(settings))

    status = client.get("/api/status")
    profile = client.get("/api/permissions/profile")

    assert status.status_code == 200
    assert status.json()["server_name"] == "obsidian-mcp"
    assert profile.json()["profile"] == "safe_write"


def test_permission_profile_can_be_updated(tmp_path: Path) -> None:
    settings = ObsidianMCPSettings(vault_path=tmp_path)
    client = TestClient(create_web_app(settings))

    response = client.put("/api/permissions/profile", json={"profile": "read_only"})

    assert response.status_code == 200
    assert response.json()["profile"] == "read_only"


def test_note_update_denied_in_read_only_profile(tmp_path: Path) -> None:
    settings = ObsidianMCPSettings(
        vault_path=tmp_path,
        permission_profile=PermissionProfile.READ_ONLY,
    )
    client = TestClient(create_web_app(settings))

    response = client.put("/api/notes/Note.md", json={"content": "Blocked"})

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "permission_denied"


def test_note_update_allowed_in_safe_write_profile(tmp_path: Path) -> None:
    (tmp_path / "Note.md").write_text("Initial", encoding="utf-8")
    settings = ObsidianMCPSettings(vault_path=tmp_path)
    client = TestClient(create_web_app(settings))

    response = client.put("/api/notes/Note.md", json={"content": "Updated"})

    assert response.status_code == 200
    assert response.json()["content"] == "Updated"


def test_notes_search_and_static_index_routes(tmp_path: Path) -> None:
    (tmp_path / "Note.md").write_text("Knowledge graph", encoding="utf-8")
    settings = ObsidianMCPSettings(vault_path=tmp_path)
    client = TestClient(create_web_app(settings))

    notes = client.get("/api/notes")
    search = client.get("/api/search", params={"q": "knowledge"})
    index = client.get("/")

    assert notes.json() == ["Note.md"]
    assert search.json()[0]["path"] == "Note.md"
    assert index.status_code == 200
    assert "Obsidian MCP" in index.text
