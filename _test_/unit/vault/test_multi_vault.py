"""Multi-vault: config, registry, router, and real-FastMCP end-to-end isolation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from obsidian_mcp.config import AdapterMode, ObsidianMCPSettings, VaultConfig, parse_vaults_spec
from obsidian_mcp.errors import UnknownVaultError
from obsidian_mcp.server import create_server
from obsidian_mcp.tools.core import register_core_tools
from obsidian_mcp.tools.knowledge import register_knowledge_tools
from obsidian_mcp.tools.plugins import register_plugin_tools
from obsidian_mcp.vault.registry import VaultRegistry, VaultRouter, build_vault_service
from obsidian_mcp.vault.service import VaultService

REGISTRARS = (register_core_tools, register_knowledge_tools, register_plugin_tools)


@pytest.fixture()
def dirs(tmp_path: Path) -> dict[str, Path]:
    out = {}
    for n in ("work", "personal", "lab"):
        (tmp_path / n).mkdir()
        out[n] = tmp_path / n
    return out


def _settings(dirs: dict[str, Path], names=("work", "personal"), **kw: Any) -> ObsidianMCPSettings:
    spec = ";".join(f"{n}={dirs[n]}" for n in names)
    return ObsidianMCPSettings(vaults=spec, _env_file=None, **kw)


def _server(dirs, names=("work", "personal")):
    settings = _settings(dirs, names)
    registry = VaultRegistry(settings.vaults, default=settings.default_vault)
    registry.start_default()
    return create_server(settings, REGISTRARS, vault_registry=registry), registry


def call(server, name: str, args: dict[str, Any] | None = None) -> Any:
    res = asyncio.run(server.call_tool(name, args or {}))
    if isinstance(res, tuple):
        res = res[0]
    return json.loads(res[0].text)


def call_error(server, name: str, args: dict[str, Any]) -> str:
    with pytest.raises(Exception) as exc:
        asyncio.run(server.call_tool(name, args))
    return str(exc.value)


# ── config ─────────────────────────────────────────────────────────────


def test_shorthand_and_json_specs_parse() -> None:
    assert parse_vaults_spec("a=/x;b=/y") == [{"name": "a", "path": "/x"}, {"name": "b", "path": "/y"}]
    assert parse_vaults_spec('a="C:\\Vaults\\A"\nb=D:\\B')[0]["path"] == "C:\\Vaults\\A"
    assert parse_vaults_spec('[{"name":"a","path":"/x"}]') == [{"name": "a", "path": "/x"}]
    assert parse_vaults_spec('{"vaults":[{"name":"a","path":"/x"}]}')[0]["name"] == "a"
    assert parse_vaults_spec("   ") == []


def test_single_vault_path_stays_backward_compatible(tmp_path: Path) -> None:
    s = ObsidianMCPSettings(vault_path=tmp_path, adapter_api_key="k", adapter_port=27150, _env_file=None)
    assert [v.name for v in s.vaults] == ["default"] and s.vault_path == tmp_path
    assert s.vaults[0].adapter_api_key == "k" and s.vaults[0].adapter_port == 27150   # inherits globals


def test_global_rest_settings_are_not_inherited_by_extra_vaults(dirs) -> None:
    s = ObsidianMCPSettings(vault_path=dirs["work"], vaults=f"personal={dirs['personal']}",
                            adapter_api_key="work-key", _env_file=None)
    by = {v.name: v for v in s.vaults}
    assert by["default"].adapter_api_key == "work-key"
    assert by["personal"].adapter_api_key == ""          # would otherwise write to the WRONG vault


def test_each_vault_keeps_its_own_rest_key_port_and_description(dirs) -> None:
    spec = json.dumps([
        {"name": "work", "path": str(dirs["work"]), "description": "Work notes",
         "adapter_api_key": "key-work", "adapter_port": 27123},
        {"name": "personal", "path": str(dirs["personal"]), "adapter_api_key": "key-personal", "adapter_port": 27125},
    ])
    s = ObsidianMCPSettings(vaults=spec, default_vault="personal", _env_file=None)
    by = {v.name: v for v in s.vaults}
    assert (by["work"].adapter_api_key, by["work"].adapter_port) == ("key-work", 27123)
    assert (by["personal"].adapter_api_key, by["personal"].adapter_port) == ("key-personal", 27125)
    assert by["work"].description == "Work notes"
    assert s.default_vault == "personal" and s.vault_path == dirs["personal"]


@pytest.mark.parametrize("kwargs,fragment", [
    ({}, "No vault configured"),
    ({"vaults": "x={work};X={personal}"}, "Duplicate vault name"),
    ({"vaults": "x={work};y={work}"}, "same folder"),
    ({"vaults": "x={work}", "default_vault": "nope"}, "not one of the configured vaults"),
    ({"vaults": "my vault={work}"}, "Invalid vault name"),
    ({"vaults": "justapath"}, "expected name=path"),
])
def test_invalid_vault_configs_are_rejected(dirs, kwargs, fragment) -> None:
    kwargs = {k: (v.format(**{n: str(p) for n, p in dirs.items()}) if isinstance(v, str) else v)
              for k, v in kwargs.items()}
    with pytest.raises(ValidationError, match=fragment):
        ObsidianMCPSettings(_env_file=None, **kwargs)


def test_two_vaults_cannot_share_one_rest_endpoint(dirs) -> None:
    spec = json.dumps([{"name": n, "path": str(dirs[n]), "adapter_api_key": "k"} for n in ("work", "personal")])
    with pytest.raises(ValidationError, match="own Local REST API port"):
        ObsidianMCPSettings(vaults=spec, _env_file=None)


def test_unknown_json_keys_are_rejected(dirs) -> None:
    with pytest.raises(ValidationError):
        ObsidianMCPSettings(vaults=json.dumps([{"name": "w", "paht": str(dirs["work"])}]), _env_file=None)


def test_vaults_load_from_environment(dirs, monkeypatch: pytest.MonkeyPatch) -> None:
    from obsidian_mcp.config import load_settings
    monkeypatch.setenv("OBSIDIAN_MCP_VAULTS", f"work={dirs['work']};personal={dirs['personal']}")
    monkeypatch.setenv("OBSIDIAN_MCP_DEFAULT_VAULT", "personal")
    monkeypatch.delenv("OBSIDIAN_MCP_VAULT_PATH", raising=False)
    s = load_settings()
    assert s.default_vault == "personal" and [v.name for v in s.vaults] == ["work", "personal"]


# ── registry / router ─────────────────────────────────────────────────


class _Spy:
    """Factory that records which VaultConfig built each service."""

    def __init__(self) -> None:
        self.built: list[VaultConfig] = []

    def __call__(self, cfg: VaultConfig) -> VaultService:
        self.built.append(cfg)
        return VaultService(cfg.path)


def test_vaults_start_lazily_and_only_once(dirs) -> None:
    spy = _Spy()
    reg = VaultRegistry(_settings(dirs, ("work", "personal", "lab")).vaults, factory=spy)
    assert spy.built == []
    reg.start_default()
    assert [c.name for c in spy.built] == ["work"]
    reg.get("personal"); reg.get("PERSONAL"); reg.current()
    assert [c.name for c in spy.built] == ["work", "personal"]       # lab never started
    reg.stop_all()


def test_active_switching_and_per_call_override(dirs) -> None:
    reg = VaultRegistry(_settings(dirs).vaults, factory=_Spy())
    assert reg.current_name() == "work"
    with reg.use("personal"):
        assert reg.current_name() == "personal"
        with reg.use("work"):
            assert reg.current_name() == "work"
        assert reg.current_name() == "personal"
    assert reg.current_name() == "work"                               # override restored
    reg.set_active("PERSONAL")
    assert reg.active_name == "personal"
    reg.stop_all()


def test_unknown_vault_error_lists_valid_names(dirs) -> None:
    reg = VaultRegistry(_settings(dirs).vaults, factory=_Spy())
    with pytest.raises(UnknownVaultError, match=r"Unknown vault 'wrk'.*work, personal"):
        reg.get("wrk")
    with pytest.raises(UnknownVaultError):
        reg.set_active("nope")
    assert reg.active_name == "work"


def test_failing_vault_does_not_poison_the_registry(dirs) -> None:
    def factory(cfg: VaultConfig) -> VaultService:
        if cfg.name == "personal":
            raise RuntimeError("Obsidian is closed")
        return VaultService(cfg.path)
    reg = VaultRegistry(_settings(dirs).vaults, factory=factory)
    reg.start_default()
    with pytest.raises(RuntimeError):
        reg.get("personal")
    assert reg.get("work") is reg.get("work")
    assert reg.describe("personal")["started"] is False
    reg.stop_all()


def test_default_factory_gives_each_vault_its_own_adapter_settings(dirs, monkeypatch) -> None:
    seen: dict[str, tuple[str, str, int]] = {}

    class FakeAdapter:
        backend_name = "FilesystemAdapter"
        def __init__(self, cfg) -> None: self.cfg = cfg

    def fake_from_settings(cfg):
        seen[cfg.name] = (cfg.adapter_api_key, cfg.adapter_host, cfg.adapter_port)
        from obsidian_mcp.adapters import AutoAdapter
        from obsidian_mcp.adapters.filesystem import FilesystemAdapter
        return AutoAdapter(FilesystemAdapter(cfg.path))

    monkeypatch.setattr("obsidian_mcp.adapters.AutoAdapter.from_settings", fake_from_settings)
    spec = json.dumps([
        {"name": "work", "path": str(dirs["work"]), "adapter_api_key": "KEY-A", "adapter_port": 27123},
        {"name": "personal", "path": str(dirs["personal"]), "adapter_api_key": "KEY-B", "adapter_port": 27125},
    ])
    s = ObsidianMCPSettings(vaults=spec, _env_file=None)
    build_vault_service(s.vaults[0]); build_vault_service(s.vaults[1])
    assert seen == {"work": ("KEY-A", "127.0.0.1", 27123), "personal": ("KEY-B", "127.0.0.1", 27125)}


def test_router_forwards_to_current_vault_and_is_read_only(dirs) -> None:
    reg = VaultRegistry(_settings(dirs).vaults, factory=_Spy())
    router = VaultRouter(reg)
    router.create_note("A", "in work")
    reg.set_active("personal")
    assert [f for f in router.list_files() if f.endswith(".md")] == []
    with reg.use("work"):
        assert router.read_note("A")["content"] == "in work"
    with pytest.raises(AttributeError):
        router.anything = 1                                            # type: ignore[attr-defined]
    router.stop()
    assert reg.describe("work")["started"] is False


# ── real FastMCP, end to end ──────────────────────────────────────────


def test_every_tool_gains_an_optional_vault_argument_and_vault_tools_exist(dirs) -> None:
    server, reg = _server(dirs)
    tools = asyncio.run(server.list_tools())
    by = {t.name: t for t in tools}
    assert {"vault_list", "vault_switch", "vault_status"} <= set(by)
    missing = [n for n, t in by.items() if not n.startswith("vault_")
               and "vault" not in t.inputSchema["properties"]]
    assert missing == []
    assert "vault" not in by["create_note"].inputSchema.get("required", [])
    assert by["create_note"].inputSchema["required"] == ["path", "content"]
    reg.stop_all()


def test_notes_land_in_the_right_vault_and_never_leak(dirs) -> None:
    server, reg = _server(dirs)
    a = call(server, "create_note", {"path": "Alpha", "content": "work note"})
    b = call(server, "create_note", {"path": "Beta", "content": "personal note", "vault": "personal"})
    assert (a["vault"], b["vault"]) == ("work", "personal")
    assert (dirs["work"] / "Alpha.md").read_text() == "work note"
    assert (dirs["personal"] / "Beta.md").read_text() == "personal note"
    assert not (dirs["work"] / "Beta.md").exists() and not (dirs["personal"] / "Alpha.md").exists()
    assert call(server, "read_note", {"path": "Beta", "vault": "PERSONAL"})["content"] == "personal note"
    assert "not found" in call_error(server, "read_note", {"path": "Beta"}).lower()   # absent from active (work) vault
    reg.stop_all()


def test_vault_switch_redirects_later_calls_but_explicit_vault_still_wins(dirs) -> None:
    server, reg = _server(dirs)
    sw = call(server, "vault_switch", {"name": "personal"})
    assert sw["previous"] == "work" and sw["name"] == "personal" and sw["active"] is True
    call(server, "create_note", {"path": "P1", "content": "x"})
    call(server, "create_note", {"path": "W1", "content": "y", "vault": "work"})
    assert (dirs["personal"] / "P1.md").exists() and (dirs["work"] / "W1.md").exists()
    assert not (dirs["work"] / "P1.md").exists() and not (dirs["personal"] / "W1.md").exists()
    listing = call(server, "vault_list")
    assert listing["active"] == "personal"
    assert {v["name"]: v["active"] for v in listing["vaults"]} == {"work": False, "personal": True}
    reg.stop_all()


def test_plugin_and_knowledge_tools_follow_the_vault_too(dirs) -> None:
    server, reg = _server(dirs)
    res = call(server, "excalidraw_generate_architecture", {
        "path": "D", "title": "D", "vault": "personal",
        "nodes": [{"id": "a", "label": "A", "type": "service"}], "edges": []})
    assert res["vault"] == "personal"
    assert (dirs["personal"] / "D.excalidraw.md").exists() and not (dirs["work"] / "D.excalidraw.md").exists()

    # knowledge tool: graph is computed from the targeted vault only
    (dirs["work"] / "Hub.md").write_text("# Hub\n[[Spoke]]\n")
    (dirs["work"] / "Spoke.md").write_text("# Spoke\n")
    (dirs["personal"] / "Diary.md").write_text("# Diary\n")
    graph_work = call(server, "build_relationship_graph", {"vault": "work"})
    graph_personal = call(server, "build_relationship_graph", {"vault": "personal"})
    titles = lambda g: {n["id"] for n in g["nodes"]}          # noqa: E731
    assert {"Hub.md", "Spoke.md"} <= titles(graph_work) and "Diary.md" not in titles(graph_work)
    assert "Diary.md" in titles(graph_personal) and "Hub.md" not in titles(graph_personal)
    assert (graph_work["vault"], graph_personal["vault"]) == ("work", "personal")
    reg.stop_all()


def test_unknown_vault_argument_gives_a_helpful_error(dirs) -> None:
    server, reg = _server(dirs)
    msg = call_error(server, "create_note", {"path": "X", "content": "y", "vault": "wrk"})
    assert "Unknown vault 'wrk'" in msg and "work, personal" in msg
    assert not list(dirs["work"].glob("X.md"))
    reg.stop_all()


def test_instructions_describe_the_vaults(dirs) -> None:
    settings = ObsidianMCPSettings(
        vaults=json.dumps([{"name": "work", "path": str(dirs["work"]), "description": "Client projects"},
                           {"name": "personal", "path": str(dirs["personal"])}]), _env_file=None)
    reg = VaultRegistry(settings.vaults, factory=_Spy())
    reg.start_default()
    server = create_server(settings, REGISTRARS, vault_registry=reg, system_prompt="BASE RULES")
    text = server.instructions
    assert text.startswith("BASE RULES") and "MULTIPLE VAULTS (2)" in text
    assert "work: Client projects" in text and "vault_switch" in text
    reg.stop_all()


def test_single_vault_registry_leaves_the_server_unchanged(dirs) -> None:
    settings = _settings(dirs, ("work",))
    reg = VaultRegistry(settings.vaults, factory=_Spy())
    server = create_server(settings, REGISTRARS, vault_registry=reg)
    tools = {t.name: t for t in asyncio.run(server.list_tools())}
    assert not any(n.startswith("vault_") for n in tools)
    assert "vault" not in tools["create_note"].inputSchema["properties"]
    assert "MULTIPLE VAULTS" not in server.instructions
    reg.stop_all()


def test_load_runtime_builds_a_registry_only_for_several_vaults(dirs, monkeypatch) -> None:
    from obsidian_mcp import __main__ as m
    monkeypatch.setenv("OBSIDIAN_MCP_VAULTS", f"work={dirs['work']};personal={dirs['personal']}")
    monkeypatch.delenv("OBSIDIAN_MCP_VAULT_PATH", raising=False)
    monkeypatch.chdir(dirs["lab"])                         # no stray .env
    settings, svc, registry, _ = m._load_runtime()
    assert registry is not None and isinstance(svc, VaultRouter) and registry.is_started("work")
    assert not registry.is_started("personal")             # lazy
    svc.stop()

    monkeypatch.delenv("OBSIDIAN_MCP_VAULTS")
    monkeypatch.setenv("OBSIDIAN_MCP_VAULT_PATH", str(dirs["work"]))
    settings, svc, registry, _ = m._load_runtime()
    assert registry is None and isinstance(svc, VaultService)
