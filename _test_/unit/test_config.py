from pathlib import Path

import pytest
from pydantic import ValidationError

from obsidian_mcp.config import LogLevel, ObsidianMCPSettings, load_settings


def test_settings_model_can_be_imported() -> None:
    assert ObsidianMCPSettings.__name__ == "ObsidianMCPSettings"


def test_settings_use_safe_defaults(tmp_path: Path) -> None:
    settings = ObsidianMCPSettings(vault_path=tmp_path)

    assert settings.vault_path == tmp_path
    assert settings.server_name == "obsidian-mcp"
    assert settings.log_level is LogLevel.INFO


def test_settings_load_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OBSIDIAN_MCP_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("OBSIDIAN_MCP_SERVER_NAME", "notes-server")
    monkeypatch.setenv("OBSIDIAN_MCP_LOG_LEVEL", "DEBUG")

    settings = load_settings()

    assert settings.vault_path == tmp_path
    assert settings.server_name == "notes-server"
    assert settings.log_level is LogLevel.DEBUG


def test_settings_reject_missing_vault_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing"

    with pytest.raises(ValidationError):
        ObsidianMCPSettings(vault_path=missing_path)
