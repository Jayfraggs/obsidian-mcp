from __future__ import annotations

import io
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
