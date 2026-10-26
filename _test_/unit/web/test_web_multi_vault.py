"""Web UI backend: vault switching and per-vault REST API keys."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.vault.registry import VaultRegistry, VaultRouter
from obsidian_mcp.vault.service import VaultService
from obsidian_mcp.web.app import create_web_app


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Two vaults with distinct REST keys; cwd is a scratch dir so .env writes are isolated."""
    work, personal = tmp_path / "Work", tmp_path / "Personal"
    work.mkdir(); personal.mkdir()
    monkeypatch.chdir(tmp_path)
    for k in ("OBSIDIAN_MCP_VAULT_PATH", "OBSIDIAN_MCP_VAULTS"):
        monkeypatch.delenv(k, raising=False)
    spec = json.dumps([
        {"name": "work", "path": str(work), "description": "Client projects",
         "adapter_api_key": "KEY-WORK-1234", "adapter_port": 27123},
        {"name": "personal", "path": str(personal), "adapter_port": 27125},
    ])
    settings = ObsidianMCPSettings(vaults=spec, _env_file=None)
    registry = VaultRegistry(settings.vaults, default=settings.default_vault)
    registry.start_default()
    client = TestClient(create_web_app(settings, vault_service=VaultRouter(registry), vault_registry=registry))
    yield client, registry, tmp_path
    registry.stop_all()


def test_vaults_endpoint_lists_vaults_without_leaking_keys(env) -> None:
    client, _, _ = env
    data = client.get("/api/vaults").json()
    assert data["multi"] is True and data["active"] == "work"
    by = {v["name"]: v for v in data["vaults"]}
    assert by["work"]["rest_key_set"] is True and by["work"]["rest_port"] == 27123
    assert by["personal"]["rest_key_set"] is False and by["personal"]["rest_port"] == 27125
    assert by["work"]["description"] == "Client projects"
    assert "KEY-WORK-1234" not in json.dumps(data)


def test_switching_vaults_redirects_the_notes_api_without_leakage(env) -> None:
    client, _, root = env
    (root / "Work" / "W.md").write_text("work")
    (root / "Personal" / "P.md").write_text("personal")
    assert client.get("/api/notes/W.md").json()["content"] == "work"
    assert client.get("/api/notes/P.md").status_code == 400            # not in the active vault

    assert client.put("/api/vaults/active", json={"name": "personal"}).json()["active"] == "personal"
    assert client.get("/api/notes/P.md").json()["content"] == "personal"
    assert client.get("/api/notes/W.md").status_code == 400

    status = client.get("/api/status").json()
    assert status["vault"] == "personal" and status["vault_path"].endswith("Personal")
    assert status["adapter_key_set"] is False                           # personal has no key, work does


def test_switching_to_an_unknown_vault_is_a_clean_404(env) -> None:
    client, _, _ = env
    r = client.put("/api/vaults/active", json={"name": "nope"})
    assert r.status_code == 404 and "work, personal" in r.json()["detail"]["message"]
    assert client.get("/api/vaults").json()["active"] == "work"


def test_each_vault_has_its_own_rest_settings(env) -> None:
    client, _, _ = env
    w = client.get("/api/settings/adapter?vault=work").json()
    p = client.get("/api/settings/adapter?vault=personal").json()
    assert (w["vault"], w["key_set"], w["port"], w["key_preview"]) == ("work", True, 27123, "*********1234")
    assert (p["vault"], p["key_set"], p["port"]) == ("personal", False, 27125)
    assert client.get("/api/settings/adapter").json()["vault"] == "work"      # defaults to active
    assert client.get("/api/settings/adapter?vault=zzz").status_code == 404


def test_saving_one_vaults_key_never_touches_the_other(env) -> None:
    client, registry, _ = env
    r = client.put("/api/settings/adapter?vault=personal",
                   json={"api_key": "KEY-PERSONAL-9999", "host": "127.0.0.1", "port": 27125})
    assert r.status_code == 200 and r.json()["vault"] == "personal"
    by = {c.name: c for c in registry.configs()}
    assert by["personal"].adapter_api_key == "KEY-PERSONAL-9999"
    assert by["work"].adapter_api_key == "KEY-WORK-1234" and by["work"].adapter_port == 27123


def test_empty_key_keeps_the_stored_key_but_explicit_clear_removes_it(env) -> None:
    client, registry, _ = env
    # UI sends null when the key box is empty and a key exists (the old UI wiped keys here)
    client.put("/api/settings/adapter?vault=work", json={"api_key": None, "host": "127.0.0.1", "port": 27130})
    cfg = {c.name: c for c in registry.configs()}["work"]
    assert cfg.adapter_api_key == "KEY-WORK-1234" and cfg.adapter_port == 27130
    client.put("/api/settings/adapter?vault=work", json={"api_key": "", "host": "127.0.0.1", "port": 27123})
    assert {c.name: c for c in registry.configs()}["work"].adapter_api_key == ""


def test_two_vaults_cannot_be_given_the_same_rest_endpoint(env) -> None:
    client, registry, _ = env
    r = client.put("/api/settings/adapter?vault=personal",
                   json={"api_key": "ANOTHER", "host": "127.0.0.1", "port": 27123})   # work's endpoint
    assert r.status_code == 400 and "own Local REST API port" in r.json()["detail"]["message"]
    assert {c.name: c for c in registry.configs()}["personal"].adapter_api_key == ""   # unchanged


def test_per_vault_keys_persist_to_env_and_reload(env) -> None:
    client, _, root = env
    client.put("/api/settings/adapter?vault=personal",
               json={"api_key": "KEY-PERSONAL-9999", "host": "127.0.0.1", "port": 27125})
    assert (root / ".env").exists()
    reloaded = ObsidianMCPSettings(_env_file=root / ".env")
    by = {v.name: v for v in reloaded.vaults}
    assert by["personal"].adapter_api_key == "KEY-PERSONAL-9999" and by["personal"].adapter_port == 27125
    assert by["work"].adapter_api_key == "KEY-WORK-1234" and by["work"].description == "Client projects"


def test_connection_test_uses_the_selected_vaults_credentials(env, monkeypatch) -> None:
    client, _, _ = env
    probed: list[tuple[str, str, int]] = []

    class FakeRest:
        def __init__(self, key, host, port): probed.append((key, host, port))
        def health_check(self): return True
        def close(self): pass

    monkeypatch.setattr("obsidian_mcp.adapters.rest_api.RestApiAdapter", FakeRest)
    assert client.post("/api/settings/adapter/test?vault=work").json() == {
        "vault": "work", "reachable": True, "reason": "OK"}
    assert probed == [("KEY-WORK-1234", "127.0.0.1", 27123)]
    r = client.post("/api/settings/adapter/test?vault=personal").json()      # no key -> never probes
    assert r["reachable"] is False and "No API key" in r["reason"] and len(probed) == 1


def test_saved_key_takes_effect_by_resetting_that_vaults_service(env) -> None:
    client, registry, _ = env
    registry.get("personal")
    assert registry.is_started("personal")
    client.put("/api/settings/adapter?vault=personal",
               json={"api_key": "K", "host": "127.0.0.1", "port": 27125})
    assert not registry.is_started("personal")        # rebuilt with the new key on next use
    assert registry.is_started("work")                # untouched


def test_single_vault_mode_is_unchanged_and_hides_the_switcher(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    settings = ObsidianMCPSettings(vault_path=tmp_path, adapter_api_key="SINGLE-KEY-1111", _env_file=None)
    client = TestClient(create_web_app(settings))
    v = client.get("/api/vaults").json()
    assert v["multi"] is False and len(v["vaults"]) == 1 and v["vaults"][0]["rest_key_set"] is True
    assert client.put("/api/vaults/active", json={"name": "x"}).status_code == 400
    # legacy behaviour: "" clears, null keeps
    client.put("/api/settings/adapter", json={"api_key": None, "host": "127.0.0.1", "port": 27123})
    assert client.get("/api/settings/adapter").json()["key_set"] is True
    client.put("/api/settings/adapter", json={"api_key": "", "host": "127.0.0.1", "port": 27123})
    assert client.get("/api/settings/adapter").json()["key_set"] is False
    assert "vault" not in client.get("/api/status").json()


def test_status_survives_an_unstartable_active_vault(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(); b.mkdir()
    settings = ObsidianMCPSettings(vaults=f"a={a};b={b}", _env_file=None)

    def factory(cfg):
        if cfg.name == "b":
            raise RuntimeError("Obsidian is closed")
        return VaultService(cfg.path)

    reg = VaultRegistry(settings.vaults, factory=factory)
    reg.start_default()
    client = TestClient(create_web_app(settings, vault_service=VaultRouter(reg), vault_registry=reg))
    client.put("/api/vaults/active", json={"name": "b"})
    s = client.get("/api/status")
    assert s.status_code == 200 and s.json()["adapter"] == "unavailable" and "closed" in s.json()["vault_error"]
    reg.stop_all()
