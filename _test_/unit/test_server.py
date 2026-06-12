from pathlib import Path

import pytest

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.server import create_server


def test_create_server_uses_configured_name(tmp_path: Path) -> None:
    settings = ObsidianMCPSettings(vault_path=tmp_path, server_name="test-server")

    server = create_server(settings)

    assert getattr(server, "name") == "test-server"


def test_build_server_returns_configured_server(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from obsidian_mcp.__main__ import build_server

    monkeypatch.setenv("OBSIDIAN_MCP_VAULT_PATH", str(tmp_path))

    server = build_server()

    assert getattr(server, "name") == "obsidian-mcp"
