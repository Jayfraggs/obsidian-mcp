"""Setup wizard: multi-vault logic (headless — customtkinter is mocked)."""

from __future__ import annotations

import json
import sys
import types
import unittest.mock as mock
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

for mod in ("customtkinter", "PIL", "PIL.Image", "PIL.ImageDraw", "pystray", "tkinter",
            "tkinter.filedialog", "tkinter.messagebox"):
    sys.modules.setdefault(mod, mock.MagicMock())

with patch("subprocess.check_call"):
    import setup_wizard as sw

from obsidian_mcp.config import ObsidianMCPSettings


@pytest.fixture()
def vdirs(tmp_path: Path) -> dict[str, Path]:
    out = {}
    for n in ("Work Vault", "Personal", "Lab"):
        (tmp_path / n).mkdir()
        out[n] = tmp_path / n
    return out


def row(name, path, key="", port="27123", host="127.0.0.1", mode="auto") -> dict[str, str]:
    return {"name": name, "path": str(path), "api_key": key, "port": port, "host": host, "mode": mode}


# ── naming ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("My Work Vault", "my-work-vault"), ("Personal", "personal"), ("  ##Lab_01 ", "lab_01"),
    ("日本語", "vault"), ("a" * 80, "a" * 48),
])
def test_slugify_vault_name(text, expected) -> None:
    assert sw.slugify_vault_name(text) == expected


# ── validation ──────────────────────────────────────────────────────

def test_valid_vault_rows_pass(vdirs) -> None:
    assert sw.validate_vault_rows([
        row("work", vdirs["Work Vault"], "KEY-A", "27123"),
        row("personal", vdirs["Personal"], "KEY-B", "27125"),
        row("lab", vdirs["Lab"]),                      # no key → direct file access, port irrelevant
    ]) is None


@pytest.mark.parametrize("name", ["", "has space", "-lead", "x" * 49])
def test_invalid_names_are_rejected(vdirs, name) -> None:
    assert "not a valid name" in sw.validate_vault_rows([row(name, vdirs["Lab"])])


def test_duplicate_names_paths_and_missing_folders_are_rejected(vdirs, tmp_path) -> None:
    assert "unique" in sw.validate_vault_rows([row("a", vdirs["Lab"]), row("A", vdirs["Personal"])])
    assert "same folder" in sw.validate_vault_rows([row("a", vdirs["Lab"]), row("b", vdirs["Lab"])])
    assert "not an existing folder" in sw.validate_vault_rows([row("a", tmp_path / "nope")])


def test_two_keyed_vaults_may_not_share_a_rest_port(vdirs) -> None:
    msg = sw.validate_vault_rows([row("work", vdirs["Work Vault"], "KEY-A", "27123"),
                                  row("personal", vdirs["Personal"], "KEY-B", "27123")])
    assert "same REST API port 27123" in msg and "own key" in msg


def test_keyed_vault_needs_a_valid_port(vdirs) -> None:
    for bad in ("", "abc", "0", "70000"):
        assert "not a valid port" in sw.validate_vault_rows([row("w", vdirs["Lab"], "K", bad)])


# ── env serialisation ───────────────────────────────────────────────

def test_shorthand_is_used_when_no_vault_needs_rest(vdirs) -> None:
    value = sw.build_vaults_env_value([row("work", vdirs["Work Vault"]), row("personal", vdirs["Personal"])])
    assert value == f"work={vdirs['Work Vault']};personal={vdirs['Personal']}"


def test_json_carries_each_vaults_own_key_and_port(vdirs) -> None:
    value = sw.build_vaults_env_value([
        row("work", vdirs["Work Vault"], "KEY-A", "27123"),
        row("personal", vdirs["Personal"], "KEY-B", "27125"),
        row("lab", vdirs["Lab"]),
    ])
    data = {e["name"]: e for e in json.loads(value)}
    assert (data["work"]["adapter_api_key"], data["work"]["adapter_port"]) == ("KEY-A", 27123)
    assert (data["personal"]["adapter_api_key"], data["personal"]["adapter_port"]) == ("KEY-B", 27125)
    assert "adapter_api_key" not in data["lab"]
    assert "\\" not in value                              # forward slashes only


def test_json_paths_use_forward_slashes_even_for_windows_paths() -> None:
    value = sw.build_vaults_env_value([{"name": "w", "path": r"C:\Vaults\Work", "api_key": "K",
                                        "port": "27123", "host": "127.0.0.1", "mode": "auto"}])
    assert json.loads(value)[0]["path"] == "C:/Vaults/Work"


def test_format_env_line_quotes_only_json_values() -> None:
    assert sw.format_env_line("A", "plain") == "A=plain"
    assert sw.format_env_line("A", "w=/x;p=/y") == "A=w=/x;p=/y"
    assert sw.format_env_line("A", '[{"d":"it\'s"}]') == "A='[{\"d\":\"it\\'s\"}]'"


def test_wizard_output_loads_back_with_each_vault_keeping_its_own_key(vdirs, tmp_path, monkeypatch) -> None:
    """The full chain: wizard rows → .env on disk → the server's real settings loader."""
    env_path = tmp_path / ".env"
    monkeypatch.setattr(sw, "get_env_path", lambda: env_path)
    rows = [row("work", vdirs["Work Vault"], "KEY-A", "27123"),
            row("personal", vdirs["Personal"], "KEY-B", "27125")]
    sw.write_env({
        "OBSIDIAN_MCP_VAULT_PATH": rows[0]["path"],
        "OBSIDIAN_MCP_ADAPTER_API_KEY": "KEY-A",
        "OBSIDIAN_MCP_VAULTS": sw.build_vaults_env_value(rows),
    })
    s = ObsidianMCPSettings(_env_file=env_path)
    by = {v.name: v for v in s.vaults}
    assert list(by) == ["work", "personal"]                                   # legacy path deduped, not doubled
    assert (by["work"].adapter_api_key, by["work"].adapter_port) == ("KEY-A", 27123)
    assert (by["personal"].adapter_api_key, by["personal"].adapter_port) == ("KEY-B", 27125)
    assert by["work"].path == vdirs["Work Vault"].resolve()                    # path with a space survives


def test_existing_write_env_behaviour_is_unchanged_for_plain_values(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    monkeypatch.setattr(sw, "get_env_path", lambda: env_path)
    sw.write_env({"OBSIDIAN_MCP_VAULT_PATH": "/some/path", "OBSIDIAN_MCP_LOG_LEVEL": "INFO"})
    text = env_path.read_text()
    assert "OBSIDIAN_MCP_VAULT_PATH=/some/path\n" in text and "OBSIDIAN_MCP_LOG_LEVEL=INFO\n" in text


# ── collecting rows from the wizard's fields ─────────────────────────────

PRIMARY = {"vault_path": "", "vault_name": "work", "adapter_api_key": "KEY-A",
           "adapter_host": "127.0.0.1", "adapter_port": "27123", "adapter_mode": "auto"}


def test_single_vault_yields_one_row_and_therefore_no_vaults_env(vdirs) -> None:
    rows = sw.collect_vault_rows({**PRIMARY, "vault_path": str(vdirs["Work Vault"])}, [])
    assert len(rows) == 1 and rows[0]["name"] == "work" and rows[0]["api_key"] == "KEY-A"


def test_extra_rows_get_their_own_key_and_port_and_untouched_rows_are_skipped(vdirs) -> None:
    rows = sw.collect_vault_rows(
        {**PRIMARY, "vault_path": str(vdirs["Work Vault"])},
        [{"name": "personal", "path": str(vdirs["Personal"]), "api_key": "KEY-B", "port": "27125"},
         {"name": "", "path": "", "api_key": "", "port": "27127"}])
    assert [r["name"] for r in rows] == ["work", "personal"]
    assert (rows[1]["api_key"], rows[1]["port"], rows[1]["mode"]) == ("KEY-B", "27125", "auto")
    assert sw.validate_vault_rows(rows) is None
    data = {e["name"]: e for e in json.loads(sw.build_vaults_env_value(rows))}
    assert data["work"]["adapter_api_key"] == "KEY-A" and data["personal"]["adapter_api_key"] == "KEY-B"


def test_primary_name_defaults_to_a_slug_of_the_folder_name(vdirs) -> None:
    rows = sw.collect_vault_rows({**PRIMARY, "vault_name": "", "vault_path": str(vdirs["Work Vault"])}, [])
    assert rows[0]["name"] == "work-vault"
    win = sw.collect_vault_rows({**PRIMARY, "vault_name": "", "vault_path": r"C:\Users\Jimi\My Notes"}, [])
    assert win[0]["name"] == "my-notes"


def test_extra_vault_with_a_missing_name_fails_validation(vdirs) -> None:
    rows = sw.collect_vault_rows({**PRIMARY, "vault_path": str(vdirs["Work Vault"])},
                                 [{"name": "", "path": str(vdirs["Personal"]), "api_key": "", "port": "27125"}])
    assert "not a valid name" in sw.validate_vault_rows(rows)


def test_to_posix_path_handles_windows_unc_and_posix_paths() -> None:
    assert sw.to_posix_path(r"C:\Vaults\Work") == "C:/Vaults/Work"
    assert sw.to_posix_path("D:/Already/Posix") == "D:/Already/Posix"
    assert sw.to_posix_path(r"\\server\share\notes") == "//server/share/notes"
    assert sw.to_posix_path("/home/me/notes") == "/home/me/notes"
