"""Both features together: the Excalidraw guard must respect the vault a call targets."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.plugins import excalidraw_scene as sc
from obsidian_mcp.server import create_server
from obsidian_mcp.tools.core import register_core_tools
from obsidian_mcp.tools.plugins import register_plugin_tools
from obsidian_mcp.vault.registry import VaultRegistry

RAW = json.dumps({"type": "excalidraw", "elements": [
    {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 50, "text": "Boxed"}]})


def _call(server, name, args):
    res = asyncio.run(server.call_tool(name, args))
    res = res[0] if isinstance(res, tuple) else res
    return json.loads(res[0].text)


def test_guarded_drawing_writes_land_in_the_targeted_vault(tmp_path: Path) -> None:
    for n in ("work", "personal"):
        (tmp_path / n).mkdir()
    settings = ObsidianMCPSettings(vaults=f"work={tmp_path/'work'};personal={tmp_path/'personal'}", _env_file=None)
    reg = VaultRegistry(settings.vaults, default=settings.default_vault)
    reg.start_default()
    server = create_server(settings, (register_core_tools, register_plugin_tools), vault_registry=reg)

    res = _call(server, "create_note", {"path": "Sketch.excalidraw.md", "content": RAW, "vault": "personal"})
    assert res["ok"] and res["repaired"] and res["vault"] == "personal"
    written = tmp_path / "personal" / "Sketch.excalidraw.md"
    assert written.exists() and not (tmp_path / "work" / "Sketch.excalidraw.md").exists()
    scene = sc.parse_drawing(written.read_text()).payload
    assert [i for i in sc.validate_scene(scene) if i.severity == "error"] == []

    # edit via the dedicated tool in the same vault, then confirm the other vault is untouched
    edit = _call(server, "excalidraw_edit_diagram", {
        "path": "Sketch.excalidraw.md", "vault": "personal",
        "add": [{"id": "b", "type": "ellipse", "label": "New"}]})
    assert edit["ok"] and edit["vault"] == "personal"
    assert list((tmp_path / "work").iterdir()) == []

    # raw prose is rejected in the targeted vault and nothing leaks anywhere
    bad = _call(server, "create_note", {"path": "Bad.excalidraw.md", "content": "oops", "vault": "work"})
    assert bad["ok"] is False and bad["vault"] == "work"
    assert list((tmp_path / "work").iterdir()) == []
    reg.stop_all()
