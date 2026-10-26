from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

from obsidian_mcp import __main__ as main_module


def test_check_config_prints_ascii_status_for_cp1252_console(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(
        vault_path=tmp_path,
        adapter_mode=SimpleNamespace(value="filesystem"),
        permission_profile=SimpleNamespace(value="admin"),
        templates_folder="Templates",
        web_port=8765,
        adapter_api_key=None,
    )
    adapter = SimpleNamespace(
        backend_name="FilesystemAdapter",
        health_check=lambda: True,
    )
    cp1252_stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")

    monkeypatch.setattr("obsidian_mcp.config.load_settings", lambda: settings)
    monkeypatch.setattr("obsidian_mcp.adapters.AutoAdapter.from_settings", lambda _: adapter)
    monkeypatch.setattr(main_module.sys, "stdout", cp1252_stdout)

    with pytest.raises(SystemExit) as exc_info:
        main_module.check_config()

    assert exc_info.value.code == 0


def test_check_config_multi_vault_reports_each_vault_and_only_fails_on_default(tmp_path, monkeypatch, capsys) -> None:
    import pytest
    from obsidian_mcp import __main__ as m
    from obsidian_mcp.config import ObsidianMCPSettings

    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OBSIDIAN_MCP_VAULT_PATH", raising=False)
    monkeypatch.setenv("OBSIDIAN_MCP_VAULTS", json.dumps([
        {"name": "a", "path": str(a)},
        {"name": "b", "path": str(b), "adapter_api_key": "K", "adapter_port": 27125, "adapter_mode": "rest"}]))
    with pytest.raises(SystemExit) as exc:                 # default vault 'a' is fine -> exit 0
        m.check_config()
    out = capsys.readouterr().out
    assert exc.value.code == 0
    assert "vault a" in out and "vault b" in out and "own REST key" in out
    assert "[WARN] Default vault is fine, but not reachable: b" in out and "All checks passed" not in out

    monkeypatch.setenv("OBSIDIAN_MCP_DEFAULT_VAULT", "b")   # now the unreachable one is the default -> exit 1
    with pytest.raises(SystemExit) as exc:
        m.check_config()
    assert exc.value.code == 1
