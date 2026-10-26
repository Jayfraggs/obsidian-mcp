from pathlib import Path

import pytest

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.server import create_server


def test_create_server_uses_configured_name(tmp_path: Path) -> None:
    settings = ObsidianMCPSettings(vault_path=tmp_path, server_name="test-server")

    server = create_server(settings)

    assert getattr(server, "name") == "test-server"


def test_startup_path_builds_a_server_from_the_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What `python -m obsidian_mcp` does: environment -> settings -> vault service -> server."""
    from obsidian_mcp.__main__ import _build_vault_service

    monkeypatch.chdir(tmp_path)                    # no stray .env
    monkeypatch.setenv("OBSIDIAN_MCP_VAULT_PATH", str(tmp_path))

    settings, vault_service, _ = _build_vault_service()
    server = create_server(settings, vault_service=vault_service)

    assert getattr(server, "name") == "obsidian-mcp"
    assert vault_service.resolver.vault_path == tmp_path.resolve()


def test_bundled_icon_exists_and_loads() -> None:
    """icon.png was referenced by server.py, pyproject and the wizard but never committed;
    _load_icon() swallows the error, so the icon silently disappeared on fresh clones."""
    import obsidian_mcp.server as srv

    assert (Path(srv.__file__).parent / "icon.png").is_file()
    assert srv._load_icon() is not None
