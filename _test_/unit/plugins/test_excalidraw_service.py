"""Tests for ExcalidrawService against a real temp vault."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_mcp.plugins import excalidraw_scene as sc
from obsidian_mcp.plugins.excalidraw import ExcalidrawService
from obsidian_mcp.vault.service import VaultService



# Real lz-string (JS) output for a 2-element scene; see test_excalidraw_scene.py
JS_SCENE = (
    "N4IgLgngDgpiBcIYA8DGBDANgSwCYCd0B3EAGhADcZ8BnbAewDsEAmcm+gV31TkXoBGdXNnTNyMTDAC2MRmBoIA2qDwIQ6AagCMLAMwAWAKxlw0PiHwxUYMQHMpp5AgAM5CK/JE8YABYJtFzcQXxhsO18wBCNggS5GXABRKVl5RXgVM1h1MBQo8jVEMGQwIKDtEABfAF1K0lVcHJKylwrySGyivKcA4I94QK8ff3gADmDQ8MjWYNyS9QAJAEvMTHoAAkBeDcAhPdN6fHDsRiwAFW7EZdWNndNUJlsj6gBJRsRNHX1jKurydCgoADKtlyCGAdRAADNsFJ0mDKkA=="
)


@pytest.fixture()
def vault(tmp_path: Path) -> VaultService:
    return VaultService(tmp_path)


@pytest.fixture()
def ex(vault: VaultService) -> ExcalidrawService:
    return ExcalidrawService(vault)


def _scene(vault: VaultService, path: str) -> dict:
    parsed = sc.parse_drawing(vault.read_note(path)["content"])
    assert parsed.payload is not None, parsed.error
    return parsed.payload


def _assert_valid(vault: VaultService, path: str) -> dict:
    scene = _scene(vault, path)
    assert [i for i in sc.validate_scene(scene) if i.severity == "error"] == []
    return scene


# ── creation ───────────────────────────────────────────────────────────


def test_create_diagram_writes_a_valid_drawing(ex, vault) -> None:
    res = ex.create_diagram("Diagrams/Flow", "Flow", [
        {"id": "a", "type": "rectangle", "label": "A"},
        {"id": "b", "type": "ellipse", "label": "B"},
        {"type": "arrow", "start": "a", "end": "b", "label": "go"},
    ])
    assert res["ok"] and res["path"] == "Diagrams/Flow.excalidraw.md"
    assert set(res["ids"]) == {"a", "b"}
    assert len(_assert_valid(vault, res["path"])["elements"]) == res["element_count"]


def test_invalid_skeleton_writes_nothing_and_lists_every_problem(ex, vault) -> None:
    res = ex.create_diagram("Bad", "Bad", [
        {"id": "a", "type": "rectangle"}, {"type": "arrow", "start": "a", "end": "zzz"},
        {"type": "blob"},
    ])
    assert res["ok"] is False and res["written"] is False
    assert len(res["problems"]) == 2 and "excalidraw_get_schema" in res["hint"]
    assert not (vault.root / "Bad.excalidraw.md").exists() if hasattr(vault, "root") else True
    assert "Bad.excalidraw.md" not in str(vault.list_files())


def test_create_refuses_to_clobber_unless_overwrite(ex) -> None:
    els = [{"id": "a", "type": "rectangle", "label": "A"}]
    ex.create_diagram("D", "D", els)
    with pytest.raises(Exception):
        ex.create_diagram("D", "D", els)
    assert ex.create_diagram("D", "D", els, overwrite=True)["ok"]


def test_empty_elements_is_a_clear_error(ex) -> None:
    assert ex.create_diagram("D", "D", [])["ok"] is False


def test_flowchart_maps_step_types_to_shapes(ex, vault) -> None:
    res = ex.generate_flowchart("Flow", "Login", [
        {"id": "s", "label": "Start", "type": "start", "next": ["c"]},
        {"id": "c", "label": "Valid?", "type": "decision",
         "next": [{"to": "ok", "label": "yes"}, {"to": "no", "label": "no"}]},
        {"id": "ok", "label": "Dashboard", "next": "e"},
        {"id": "no", "label": "Show error", "next": ["e"]},
        {"id": "e", "label": "End", "type": "end"},
    ])
    assert res["ok"]
    scene = _assert_valid(vault, res["path"])
    kinds = {e["customData"]["handle"]: e["type"] for e in scene["elements"] if e["type"] in sc.SHAPE_TYPES}
    assert kinds == {"s": "ellipse", "c": "diamond", "ok": "rectangle", "no": "rectangle", "e": "ellipse"}
    assert len([e for e in scene["elements"] if e["type"] == "arrow"]) == 5


def test_flowchart_reports_bad_targets_and_types(ex) -> None:
    res = ex.generate_flowchart("F", "F", [
        {"id": "a", "type": "banana", "next": ["b"]},
        {"id": "b", "next": ["nowhere"]},
    ])
    assert res["ok"] is False and any("banana" in p for p in res["problems"])
    res = ex.generate_flowchart("F", "F", [{"id": "b", "next": ["nowhere"]}])
    assert any("'nowhere' not found" in p for p in res["problems"])


def test_architecture_uses_types_and_reports_unknown_edge_nodes(ex, vault) -> None:
    res = ex.generate_architecture("Arch", "Arch", [
        {"id": "web", "label": "Web", "type": "service"},
        {"id": "db", "label": "DB", "type": "database"},
    ], [{"from": "web", "to": "db", "label": "SQL"}])
    assert res["ok"]
    scene = _assert_valid(vault, res["path"])
    assert {e["type"] for e in scene["elements"]} >= {"rectangle", "ellipse", "arrow", "text"}

    bad = ex.generate_architecture("Arch2", "Arch2", [{"id": "web"}], [{"from": "web", "to": "ghost"}])
    assert bad["ok"] is False and "'ghost' not found" in " ".join(bad["problems"])
    assert "Arch2" not in str(vault.list_files())


@pytest.mark.parametrize("layout", ["layered", "grid", "radial"])
def test_architecture_layouts_all_produce_valid_scenes(ex, vault, layout) -> None:
    nodes = [{"id": f"n{i}", "label": f"Node {i}"} for i in range(5)]
    edges = [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(4)]
    res = ex.generate_architecture(f"A_{layout}", "A", nodes, edges, layout=layout)
    _assert_valid(vault, res["path"])


def test_concept_map_leaves_do_not_overlap_and_are_valid(ex, vault) -> None:
    branches = [{"label": f"Branch {i}", "children": [f"Leaf {i}.{j}" for j in range(4)]} for i in range(6)]
    res = ex.generate_concept_map("Map", "Core idea", branches)
    scene = _assert_valid(vault, res["path"])
    boxes = [e for e in scene["elements"] if e["type"] in sc.SHAPE_TYPES]
    assert len(boxes) == 1 + 6 + 24
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            assert (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"]
                    or a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"]), (a["id"], b["id"])


# ── reading / validating ──────────────────────────────────────────────


def test_parse_elements_compact_and_full(ex) -> None:
    ex.create_diagram("P", "P", [{"id": "a", "type": "rectangle", "label": "A"},
                                 {"id": "b", "type": "rectangle", "label": "B"},
                                 {"type": "arrow", "start": "a", "end": "b"}])
    compact = ex.parse_elements("P.excalidraw.md", compact=True)
    assert "elements" not in compact
    assert [n["label"] for n in compact["nodes"]] == ["A", "B"]
    assert compact["connections"][0]["from"] == "a"
    assert len(ex.parse_elements("P.excalidraw.md")["elements"]) == compact["element_count"]


def _write_compressed(vault: VaultService, path: str = "Comp.excalidraw.md") -> str:
    vault.create_note(path, (
        "---\nexcalidraw-plugin: parsed\n---\n# Excalidraw Data\n\n## Text Elements\n"
        "Héllo 🙂 ^txt00001\n\n## Embedded Files\nimg1: [[pic.png]]\n\n"
        f"%%\n## Drawing\n```compressed-json\n{JS_SCENE}\n```\n%%\n"))
    return path


def test_compressed_drawings_parse(ex, vault) -> None:
    path = _write_compressed(vault)
    res = ex.parse_elements(path)
    assert res["compressed"] is True and res["element_count"] == 2


def test_validate_and_repair_a_broken_drawing_in_place(ex, vault) -> None:
    broken = {"type": "excalidraw", "elements": [
        {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 50, "text": "Alpha"}]}
    vault.create_note("Broken.excalidraw.md",
                      "---\nexcalidraw-plugin: parsed\n---\n%%\n## Drawing\n```json\n" + json.dumps(broken) + "\n```\n%%\n")
    before = ex.validate_drawing("Broken.excalidraw.md")
    assert before["ok"] is False and any(i["code"] == "inline_label" for i in before["issues"])
    after = ex.validate_drawing("Broken.excalidraw.md", repair=True)
    assert after["ok"] and after["repaired"] and after["changes"]
    _assert_valid(vault, "Broken.excalidraw.md")
    assert "Alpha ^" in vault.read_note("Broken.excalidraw.md")["content"]


def test_validate_reports_unreadable_files(ex, vault) -> None:
    vault.create_note("Junk.excalidraw.md", "just prose")
    res = ex.validate_drawing("Junk.excalidraw.md")
    assert res["ok"] is False and res["error"]


# ── editing ───────────────────────────────────────────────────────────


@pytest.fixture()
def drawn(ex) -> str:
    ex.create_diagram("E", "E", [
        {"id": "a", "type": "rectangle", "label": "A"}, {"id": "b", "type": "rectangle", "label": "B"},
        {"id": "c", "type": "rectangle", "label": "C"},
        {"type": "arrow", "start": "a", "end": "b", "label": "ab"},
        {"type": "arrow", "start": "b", "end": "c"},
    ])
    return "E.excalidraw.md"


def test_edit_add_connects_to_existing_nodes_and_places_below(ex, vault, drawn) -> None:
    before = _scene(vault, drawn)
    low = max(e["y"] + e["height"] for e in before["elements"])
    res = ex.edit_diagram(drawn, add=[{"id": "d", "type": "ellipse", "label": "D"},
                                      {"type": "arrow", "start": "c", "end": "d", "label": "cd"}])
    assert res["ok"], res
    scene = _assert_valid(vault, drawn)
    d = next(e for e in scene["elements"] if e["id"] == res["ids"]["d"])
    assert d["y"] >= low
    c = next(e for e in scene["elements"] if (e.get("customData") or {}).get("handle") == "c")
    assert sum(1 for r in c["boundElements"] if r["type"] == "arrow") == 2    # b→c and c→d


def test_edit_remove_cascades_labels_and_attached_arrows(ex, vault, drawn) -> None:
    res = ex.edit_diagram(drawn, remove_ids=["b"])
    assert res["ok"]
    scene = _assert_valid(vault, drawn)
    assert [e["type"] for e in scene["elements"]].count("arrow") == 0      # both arrows touched b
    assert {e["originalText"] for e in scene["elements"] if e["type"] == "text"} == {"A", "C"}


def test_edit_update_relabels_and_restyles(ex, vault, drawn) -> None:
    res = ex.edit_diagram(drawn, update={"a": {"label": "Renamed with a much longer title",
                                                "backgroundColor": "#fff3bf"}})
    assert res["ok"]
    scene = _assert_valid(vault, drawn)
    a = next(e for e in scene["elements"] if (e.get("customData") or {}).get("handle") == "a")
    assert a["backgroundColor"] == "#fff3bf"
    assert "Renamed with a much longer title" in {e.get("originalText") for e in scene["elements"]}
    assert "Renamed with a much longer title ^" in vault.read_note(drawn)["content"]


def test_edit_is_all_or_nothing(ex, vault, drawn) -> None:
    before = vault.read_note(drawn)["content"]
    res = ex.edit_diagram(drawn, remove_ids=["a"], update={"zzz": {"label": "x"}, "b": {"x": 5}},
                          add=[{"type": "arrow", "start": "b", "end": "nope"}])
    assert res["ok"] is False and len(res["problems"]) == 3
    assert vault.read_note(drawn)["content"] == before


def test_edit_repairs_legacy_scene_then_edits_and_preserves_embedded_files(ex, vault) -> None:
    path = _write_compressed(vault)
    res = ex.edit_diagram(path, add=[{"id": "n", "type": "rectangle", "label": "New"}])
    assert res["ok"], res
    content = vault.read_note(path)["content"]
    assert "## Embedded Files\nimg1: [[pic.png]]" in content
    assert "```compressed-json" not in content          # rewritten as plain json
    _assert_valid(vault, path)


def test_add_annotation_on_compressed_drawing(ex, vault) -> None:
    path = _write_compressed(vault)
    res = ex.add_text_annotation(path, "A note", x=10, y=300)
    assert res["ok"] and len(res["element_id"]) == 8
    assert "A note ^" + res["element_id"] in vault.read_note(path)["content"]


# ── the guard: the original failure mode ──────────────────────────────

RAW_LLM_JSON = json.dumps({"type": "excalidraw", "version": 2, "elements": [
    {"id": "1", "type": "rectangle", "x": 0, "y": 0, "width": 120, "height": 60, "text": "Hello"},
    {"id": "2", "type": "rectangle", "x": 300, "y": 0, "width": 120, "height": 60, "text": "World"},
    {"id": "3", "type": "arrow", "x": 120, "y": 30, "points": [[0, 0], [180, 0]],
     "startBinding": {"elementId": "1"}, "endBinding": {"elementId": "2"}},
]})


def test_write_raw_repairs_bare_scene_json(ex, vault) -> None:
    res = ex.write_raw("Raw.excalidraw.md", RAW_LLM_JSON)
    assert res["ok"] and res["repaired"]
    scene = _assert_valid(vault, "Raw.excalidraw.md")
    assert {e["originalText"] for e in scene["elements"] if e["type"] == "text"} == {"Hello", "World"}
    assert vault.read_note("Raw.excalidraw.md")["content"].startswith("---\nexcalidraw-plugin: parsed")


def test_write_raw_repairs_a_hand_written_markdown_drawing(ex, vault) -> None:
    body = "# My drawing\n\n%%\n## Drawing\n```json\n" + RAW_LLM_JSON + "\n```\n%%\n"
    res = ex.write_raw("Hand.excalidraw.md", body)           # note: no frontmatter at all
    assert res["ok"]
    content = vault.read_note("Hand.excalidraw.md")["content"]
    assert "excalidraw-plugin: parsed" in content and "# My drawing" in content
    _assert_valid(vault, "Hand.excalidraw.md")


def test_write_raw_rejects_prose_and_broken_json_without_writing(ex, vault) -> None:
    for junk in ("Here is your diagram!", "{ not json", "## Drawing\n```json\n{oops\n```"):
        res = ex.write_raw("Junk.excalidraw.md", junk)
        assert res["ok"] is False and res["written"] is False and "excalidraw_create_diagram" in res["hint"]
    assert "Junk" not in str(vault.list_files())


def test_write_raw_update_mode_replaces_existing(ex, vault) -> None:
    ex.write_raw("U.excalidraw.md", RAW_LLM_JSON)
    res = ex.write_raw("U.excalidraw.md", json.dumps({"type": "excalidraw", "elements": []}), mode="update")
    assert res["ok"] and _scene(vault, "U.excalidraw.md")["elements"] == []


def test_schema_example_is_itself_buildable(ex, vault) -> None:
    res = ex.create_diagram("Schema", "Schema", ex.get_schema()["example"])
    assert res["ok"]
    _assert_valid(vault, res["path"])
