"""Tool-registration level tests: new tools exist and core note tools guard drawings."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.plugins import excalidraw_scene as sc
from obsidian_mcp.tools.core import register_core_tools
from obsidian_mcp.tools.plugins import PLUGIN_TOOL_NAMES, register_plugin_tools


class FakeMCPServer:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, name: str):
        def deco(fn):
            self.tools[name] = fn
            return fn
        return deco


def _servers(tmp_path: Path) -> FakeMCPServer:
    server = FakeMCPServer()
    settings = ObsidianMCPSettings(vault_path=tmp_path)
    register_core_tools(server, settings)
    register_plugin_tools(server, settings)
    return server


def test_every_declared_plugin_tool_is_registered(tmp_path: Path) -> None:
    server = _servers(tmp_path)
    assert set(PLUGIN_TOOL_NAMES) <= set(server.tools)
    for name in ("excalidraw_get_schema", "excalidraw_create_diagram", "excalidraw_generate_flowchart",
                 "excalidraw_edit_diagram", "excalidraw_validate"):
        assert name in PLUGIN_TOOL_NAMES


def test_create_note_on_a_drawing_goes_through_the_repairing_guard(tmp_path: Path) -> None:
    t = _servers(tmp_path).tools
    raw = ('{"type":"excalidraw","elements":[{"id":"a","type":"rectangle","x":0,"y":0,'
           '"width":100,"height":50,"text":"Boxed"}]}')
    res = t["create_note"]("Sketch.excalidraw.md", raw)
    assert res["ok"] and res["repaired"]
    scene = sc.parse_drawing(t["read_note"]("Sketch.excalidraw.md")["content"]).payload
    assert [i for i in sc.validate_scene(scene) if i.severity == "error"] == []


def test_create_note_on_a_drawing_rejects_prose(tmp_path: Path) -> None:
    t = _servers(tmp_path).tools
    res = t["create_note"]("Nope.excalidraw.md", "I drew you a nice diagram")
    assert res["ok"] is False and "excalidraw_create_diagram" in res["hint"]
    assert t["list_files"]() == [] or "Nope" not in str(t["list_files"]())


def test_append_and_str_replace_are_blocked_on_drawings_but_not_on_notes(tmp_path: Path) -> None:
    t = _servers(tmp_path).tools
    t["excalidraw_create_diagram"]("D", "D", [{"id": "a", "type": "rectangle", "label": "A"}])
    before = t["read_note"]("D.excalidraw.md")["content"]
    assert t["append_note"]("D.excalidraw.md", "junk")["ok"] is False
    assert t["str_replace_note"]("D.excalidraw.md", "A", "B")["ok"] is False
    assert t["read_note"]("D.excalidraw.md")["content"] == before
    # regular notes are untouched by the guard
    t["create_note"]("Plain", "hello")
    t["append_note"]("Plain", " world")
    content = t["read_note"]("Plain")["content"]
    assert content.startswith("hello") and content.endswith("world")


def test_regular_markdown_notes_still_use_the_plain_path(tmp_path: Path) -> None:
    t = _servers(tmp_path).tools
    # mentions "excalidraw" but is not a drawing path → untouched by the guard
    assert t["create_note"]("Excalidraw tips", "plain prose")["path"] == "Excalidraw tips.md"
    assert t["create_note"]("Normal", "x")["path"] == "Normal.md"


def test_end_to_end_tool_flow_create_edit_validate_embed(tmp_path: Path) -> None:
    t = _servers(tmp_path).tools
    schema = t["excalidraw_get_schema"]()
    assert t["excalidraw_create_diagram"]("Flow", "Flow", schema["example"])["ok"]
    nodes = t["excalidraw_parse_elements"]("Flow.excalidraw.md", compact=True)["nodes"]
    assert {n["handle"] for n in nodes} == {"user", "api", "db"}
    assert t["excalidraw_edit_diagram"]("Flow.excalidraw.md", update={"db": {"label": "Postgres 16"}})["ok"]
    assert t["excalidraw_validate"]("Flow.excalidraw.md")["ok"]
    assert "Flow.excalidraw" in t["excalidraw_embed_in_note"]("Flow.excalidraw.md", "Index")["content"]
