"""Tests for the Excalidraw scene engine (pure data, no vault)."""

from __future__ import annotations

import json

import pytest

from obsidian_mcp.plugins import excalidraw_scene as sc

# Produced by the real JS lz-string library (compressToBase64) — ground truth.
JS_SMALL = ("BYS4NmD2AEi8G4QnvQO4DeBOYAmQ", "héllo 🙂 wörld")
JS_SCENE = (
    "N4IgLgngDgpiBcIYA8DGBDANgSwCYCd0B3EAGhADcZ8BnbAewDsEAmcm+gV31TkXoBGdXNnTNyMTDAC2MRmBoIA2qDwIQ6AagCMLAMwAWAKxlw0PiHwxUYMQHMpp5AgAM5CK/JE8YABYJtFzcQXxhsO18wBCNggS5GXABRKVl5RXgVM1h1MBQo8jVEMGQwIKDtEABfAF1K0lVcHJKylwrySGyivKcA4I94QK8ff3gADmDQ8MjWYNyS9QAJAEvMTHoAAkBeDcAhPdN6fHDsRiwAFW7EZdWNndNUJlsj6gBJRsRNHX1jKurydCgoADKtlyCGAdRAADNsFJ0mDKkA=="
)


def _shapes(elements):
    return [e for e in elements if e["type"] in sc.SHAPE_TYPES]


def _overlap(a, b) -> bool:
    return not (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"]
                or a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])


# ── LZ-string ──────────────────────────────────────────────────────────


def test_lz_decompress_matches_js_ground_truth_including_astral_chars() -> None:
    assert sc.lz_decompress_base64(JS_SMALL[0]) == JS_SMALL[1]


def test_lz_decompress_rejects_garbage_without_raising() -> None:
    assert sc.lz_decompress_base64("") is None
    assert sc.lz_decompress_base64("!!!not base64!!!") in (None, "")


def test_parse_drawing_reads_compressed_json_block() -> None:
    md = f"---\nexcalidraw-plugin: parsed\n---\n# Excalidraw Data\n\n## Text Elements\n%%\n## Drawing\n```compressed-json\n{JS_SCENE[:40]}\n{JS_SCENE[40:]}\n```\n%%\n"
    parsed = sc.parse_drawing(md)
    assert parsed.compressed is True
    assert parsed.payload is not None
    assert [e["id"] for e in parsed.payload["elements"]] == ["abc12345", "txt00001"]
    assert parsed.payload["elements"][1]["text"] == "Héllo 🙂"


# ── build_elements ─────────────────────────────────────────────────────

SKELETON = [
    {"id": "user", "type": "ellipse", "label": "User"},
    {"id": "api", "type": "rectangle", "label": "API Gateway"},
    {"id": "db", "type": "diamond", "label": "Is it cached?"},
    {"type": "arrow", "start": "user", "end": "api", "label": "HTTPS"},
    {"type": "arrow", "start": "api", "end": "db"},
]


def test_built_scene_has_no_validation_issues() -> None:
    built = sc.build_elements(SKELETON)
    assert sc.validate_scene(sc.scene_payload(built.elements)) == []


def test_labels_are_bound_text_elements_not_inline_text() -> None:
    built = sc.build_elements(SKELETON)
    by_id = {e["id"]: e for e in built.elements}
    for shape in _shapes(built.elements):
        assert "text" not in shape
        texts = [by_id[r["id"]] for r in shape["boundElements"] if r["type"] == "text"]
        assert len(texts) == 1
        assert texts[0]["containerId"] == shape["id"]
    assert len([e for e in built.elements if e["type"] == "text"]) == 4  # 3 shapes + 1 arrow label


def test_arrow_bindings_are_two_way() -> None:
    built = sc.build_elements(SKELETON)
    by_id = {e["id"]: e for e in built.elements}
    arrows = [e for e in built.elements if e["type"] == "arrow"]
    assert len(arrows) == 2
    for a in arrows:
        for side in ("startBinding", "endBinding"):
            target = by_id[a[side]["elementId"]]
            assert {"id": a["id"], "type": "arrow"} in target["boundElements"]


def test_arrow_points_are_relative_and_tips_sit_outside_shapes() -> None:
    built = sc.build_elements([
        {"id": "a", "type": "rectangle", "label": "A", "x": 0, "y": 0, "width": 100, "height": 50},
        {"id": "b", "type": "rectangle", "label": "B", "x": 300, "y": 0, "width": 100, "height": 50},
        {"type": "arrow", "start": "a", "end": "b"},
    ])
    arrow = next(e for e in built.elements if e["type"] == "arrow")
    assert arrow["points"][0] == [0, 0]
    assert arrow["x"] == 100 + sc.BIND_GAP          # right edge of A + gap
    assert arrow["x"] + arrow["points"][1][0] == 300 - sc.BIND_GAP
    assert arrow["width"] == arrow["points"][1][0]


def test_text_ids_are_8_alphanumeric_characters() -> None:
    built = sc.build_elements(SKELETON)
    for e in built.elements:
        if e["type"] == "text":
            assert len(e["id"]) == 8 and e["id"].isalnum()


def test_handles_map_to_element_ids_and_survive_in_custom_data() -> None:
    built = sc.build_elements(SKELETON)
    assert set(built.ids) == {"user", "api", "db"}
    api = next(e for e in built.elements if e["id"] == built.ids["api"])
    assert api["customData"]["handle"] == "api"


def test_build_is_deterministic() -> None:
    assert sc.build_elements(SKELETON).elements == sc.build_elements(SKELETON).elements


def test_long_labels_wrap_and_grow_the_shape() -> None:
    long = "Authentication and authorisation service for every tenant"
    built = sc.build_elements([{"id": "s", "type": "rectangle", "label": long}])
    shape = _shapes(built.elements)[0]
    text = next(e for e in built.elements if e["type"] == "text")
    assert "\n" in text["text"] and text["originalText"] == long
    assert text["width"] <= shape["width"] - 2 * sc.PAD + 1
    assert text["height"] <= shape["height"] - 2 * sc.PAD + 1


def test_aliases_from_to_and_text_are_accepted() -> None:
    built = sc.build_elements([
        {"id": "a", "type": "rectangle", "text": "A"},
        {"id": "b", "type": "rectangle", "text": "B"},
        {"type": "arrow", "from": "a", "to": "b"},
    ])
    assert sc.validate_scene(sc.scene_payload(built.elements)) == []
    assert len([e for e in built.elements if e["type"] == "text"]) == 2


def test_skeleton_errors_are_all_reported_at_once() -> None:
    with pytest.raises(sc.SkeletonError) as exc:
        sc.build_elements([
            {"id": "a", "type": "rectangle", "label": "A"},
            {"id": "a", "type": "rectangle", "label": "dup"},
            {"id": "c", "type": "hexagon"},
            {"type": "arrow", "start": "a", "end": "ghost"},
            {"type": "arrow", "start": "a"},
            {"type": "arrow", "start": "a", "end": "a"},
        ])
    msg = " | ".join(exc.value.problems)
    assert "duplicate id 'a'" in msg
    assert "unsupported type 'hexagon'" in msg
    assert "'ghost' not found" in msg and "Known ids" in msg
    assert "missing 'end'" in msg
    assert "self-loops" in msg
    assert len(exc.value.problems) == 5


def test_antiparallel_arrows_do_not_overlap() -> None:
    built = sc.build_elements([
        {"id": "a", "type": "rectangle", "label": "A"},
        {"id": "b", "type": "rectangle", "label": "B"},
        {"type": "arrow", "start": "a", "end": "b"},
        {"type": "arrow", "start": "b", "end": "a"},
    ])
    arrows = [e for e in built.elements if e["type"] == "arrow"]
    assert (arrows[0]["x"], arrows[0]["y"]) != (arrows[1]["x"] + arrows[1]["points"][1][0],
                                                 arrows[1]["y"] + arrows[1]["points"][1][1])
    assert arrows[0]["y"] != arrows[1]["y"] or arrows[0]["x"] != arrows[1]["x"]


# ── layout ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("direction", ["TB", "LR"])
def test_layered_layout_never_overlaps_and_respects_direction(direction: str) -> None:
    skel = [{"id": n, "type": "rectangle", "label": n} for n in "abcdefg"]
    for s, t in [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e"), ("d", "f"), ("f", "g")]:
        skel.append({"type": "arrow", "start": s, "end": t})
    built = sc.build_elements(skel, direction=direction)
    shapes = {e["customData"]["handle"]: e for e in _shapes(built.elements)}
    axis = "y" if direction == "TB" else "x"
    assert shapes["a"][axis] < shapes["b"][axis] < shapes["d"][axis] < shapes["f"][axis] < shapes["g"][axis]
    sl = list(shapes.values())
    assert not any(_overlap(sl[i], sl[j]) for i in range(len(sl)) for j in range(i + 1, len(sl)))


def test_layered_layout_survives_cycles() -> None:
    built = sc.build_elements([
        {"id": "a", "type": "rectangle", "label": "A"},
        {"id": "b", "type": "rectangle", "label": "B"},
        {"id": "c", "type": "rectangle", "label": "C"},
        {"type": "arrow", "start": "a", "end": "b"},
        {"type": "arrow", "start": "b", "end": "c"},
        {"type": "arrow", "start": "c", "end": "a"},
    ])
    assert len(_shapes(built.elements)) == 3


def test_many_unconnected_nodes_fall_back_to_a_grid_without_overlap() -> None:
    built = sc.build_elements([{"id": f"n{i}", "type": "rectangle", "label": f"Node {i}"} for i in range(12)])
    sl = _shapes(built.elements)
    assert not any(_overlap(sl[i], sl[j]) for i in range(len(sl)) for j in range(i + 1, len(sl)))


# ── validate / repair ──────────────────────────────────────────────────

BROKEN = {
    "type": "excalidraw",
    "elements": [
        {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 50, "text": "Alpha"},
        {"id": "b", "type": "rectangle", "x": 300, "y": 0, "width": 100, "height": 50, "text": "Beta"},
        {"id": "e1", "type": "arrow", "x": 100, "y": 25, "points": [[100, 25], [300, 25]],
         "startBinding": {"elementId": "a"}, "endBinding": {"elementId": "b"}, "text": "calls"},
    ],
}


def test_validate_flags_the_classic_llm_mistakes() -> None:
    codes = {i.code for i in sc.validate_scene(BROKEN)}
    assert {"inline_label", "one_way_binding", "missing_defaults"} <= codes


def test_repair_fixes_everything_and_result_validates_clean() -> None:
    fixed, changes = sc.repair_scene(BROKEN)
    assert [i for i in sc.validate_scene(fixed) if i.severity == "error"] == []
    assert any("converted inline label" in c for c in changes)
    by_id = {e["id"]: e for e in fixed["elements"]}
    texts = sorted(e["originalText"] for e in fixed["elements"] if e["type"] == "text")
    assert texts == ["Alpha", "Beta", "calls"]
    assert all("text" not in by_id[i] for i in ("a", "b", "e1"))
    assert {"id": "e1", "type": "arrow"} in by_id["a"]["boundElements"]


def test_repair_treats_absolute_points_duplicated_in_xy_as_absolute() -> None:
    fixed, _ = sc.repair_scene(BROKEN)
    arrow = next(e for e in fixed["elements"] if e["id"] == "e1")
    assert (arrow["x"], arrow["y"]) == (100, 25)
    assert arrow["points"] == [[0, 0], [200, 0]]
    assert (arrow["width"], arrow["height"]) == (200, 0)


def test_repair_does_not_mutate_its_input() -> None:
    snapshot = json.dumps(BROKEN, sort_keys=True)
    sc.repair_scene(BROKEN)
    assert json.dumps(BROKEN, sort_keys=True) == snapshot


def test_repair_keeps_unknown_element_types_untouched() -> None:
    pl = {"type": "excalidraw", "elements": [{"id": "w", "type": "weirdthing", "x": 1, "y": 2, "foo": "bar"}]}
    fixed, _ = sc.repair_scene(pl)
    assert fixed["elements"][0] == {"id": "w", "type": "weirdthing", "x": 1, "y": 2, "foo": "bar"}


def test_repair_drops_dangling_references_and_orphan_text() -> None:
    pl = {"type": "excalidraw", "elements": [
        {"id": "a", "type": "rectangle", "x": 0, "y": 0, "width": 10, "height": 10,
         "boundElements": [{"id": "ghost", "type": "arrow"}]},
        {"id": "t1234567", "type": "text", "x": 0, "y": 0, "width": 10, "height": 10,
         "text": "x", "containerId": "nowhere"},
    ]}
    fixed, _ = sc.repair_scene(pl)
    assert fixed["elements"][0]["boundElements"] == []
    assert fixed["elements"][1]["containerId"] is None


def test_repair_rekeys_text_ids_that_are_not_eight_chars() -> None:
    pl = {"type": "excalidraw", "elements": [
        {"id": "box", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 50,
         "boundElements": [{"type": "text", "id": "lbl"}]},
        {"id": "lbl", "type": "text", "x": 0, "y": 0, "width": 10, "height": 10,
         "text": "hi", "containerId": "box"},
    ]}
    fixed, _ = sc.repair_scene(pl)
    new_id = next(e["id"] for e in fixed["elements"] if e["type"] == "text")
    assert len(new_id) == 8
    assert fixed["elements"][0]["boundElements"] == [{"type": "text", "id": new_id}]


def test_repair_rejects_non_scenes() -> None:
    with pytest.raises(ValueError):
        sc.repair_scene([1, 2, 3])
    with pytest.raises(ValueError):
        sc.repair_scene({"type": "excalidraw"})


# ── file I/O ───────────────────────────────────────────────────────────


def test_canonical_file_roundtrips_and_lists_text_elements() -> None:
    built = sc.build_elements(SKELETON)
    payload = sc.scene_payload(built.elements)
    md = sc.build_drawing_file("My Diagram", payload)
    assert md.startswith("---\nexcalidraw-plugin: parsed\n")
    assert "# Excalidraw Data" in md and "## Text Elements" in md
    for e in built.elements:
        if e["type"] == "text":
            assert f"{e['originalText']} ^{e['id']}" in md
    assert sc.parse_drawing(md).payload == json.loads(json.dumps(payload))


def test_rewrite_preserves_embedded_files_and_user_markdown() -> None:
    original = (
        "---\nexcalidraw-plugin: parsed\n---\n\nMy own notes above the data.\n\n"
        "# Excalidraw Data\n\n## Text Elements\nold text ^oldoldol\n\n"
        "## Embedded Files\nabc123: [[pic.png]]\n\n"
        "%%\n## Drawing\n```json\n{\"type\": \"excalidraw\", \"elements\": []}\n```\n%%\n"
    )
    payload = sc.scene_payload(sc.build_elements([{"id": "a", "type": "rectangle", "label": "New"}]).elements)
    out = sc.rewrite_drawing_file(original, payload)
    assert "My own notes above the data." in out
    assert "## Embedded Files\nabc123: [[pic.png]]" in out
    assert "old text ^oldoldol" not in out and "New ^" in out
    assert sc.parse_drawing(out).payload["elements"][0]["type"] == "rectangle"


def test_rewrite_adds_text_section_to_legacy_files_without_one() -> None:
    legacy = ("---\nexcalidraw-plugin: parsed\n---\n\n# T\n\n%%\n## Drawing\n```json\n"
              "{\"type\":\"excalidraw\",\"elements\":[]}\n```\n%%\n")
    payload = sc.scene_payload(sc.build_elements([{"id": "a", "type": "text", "text": "hello"}]).elements)
    out = sc.rewrite_drawing_file(legacy, payload)
    assert "## Text Elements\nhello ^" in out
    assert out.index("## Text Elements") < out.index("## Drawing")


def test_parse_drawing_reports_useful_errors() -> None:
    assert "No \"## Drawing\" block" in sc.parse_drawing("# nothing here").error
    assert "invalid" in sc.parse_drawing("## Drawing\n```json\n{oops\n```").error.lower()


def test_ensure_plugin_frontmatter_variants() -> None:
    assert sc.ensure_plugin_frontmatter("body").startswith("---\nexcalidraw-plugin: parsed")
    assert "excalidraw-plugin: parsed" in sc.ensure_plugin_frontmatter("---\ntags: [a]\n---\nbody")
    already = "---\nexcalidraw-plugin: parsed\n---\nbody"
    assert sc.ensure_plugin_frontmatter(already) == already


def test_summarize_scene_is_compact_and_uses_handles() -> None:
    built = sc.build_elements(SKELETON)
    summary = sc.summarize_scene(sc.scene_payload(built.elements))
    assert {n["label"] for n in summary["nodes"]} == {"User", "API Gateway", "Is it cached?"}
    assert {(c["from"], c["to"], c["label"]) for c in summary["connections"]} == {
        ("user", "api", "HTTPS"), ("api", "db", "")}


# ── regressions found by rendering generated diagrams ─────────────────


def _abs_points(arrow):
    return [(arrow["x"] + px, arrow["y"] + py) for px, py in arrow["points"]]


def test_long_edges_are_routed_around_intervening_shapes() -> None:
    skel = [{"id": n, "type": "rectangle", "label": n.upper()} for n in "abcd"]
    skel += [{"type": "arrow", "start": s, "end": t} for s, t in
             [("a", "b"), ("b", "c"), ("c", "d"), ("a", "d")]]
    built = sc.build_elements(skel, direction="LR")
    by_id = {e["id"]: e for e in built.elements}
    shapes = _shapes(built.elements)
    arrows = [e for e in built.elements if e["type"] == "arrow"]
    bent = [a for a in arrows if len(a["points"]) == 3]
    assert len(bent) == 1 and bent[0]["roundness"] == {"type": 2}      # only a→d needed rerouting
    for a in arrows:
        ends = {a["startBinding"]["elementId"], a["endBinding"]["elementId"]}
        others = [s for s in shapes if s["id"] not in ends]
        pts = _abs_points(a)
        for p0, p1 in zip(pts, pts[1:]):
            assert not sc._blocked(p0, p1, others, 0), f"arrow {a['id']} crosses a shape"
    # bound endpoints must still reference the right shapes
    assert by_id[bent[0]["startBinding"]["elementId"]]["customData"]["handle"] == "a"
    assert by_id[bent[0]["endBinding"]["elementId"]]["customData"]["handle"] == "d"


def test_clear_arrows_stay_straight() -> None:
    built = sc.build_elements([
        {"id": "a", "type": "rectangle", "label": "A"}, {"id": "b", "type": "rectangle", "label": "B"},
        {"type": "arrow", "start": "a", "end": "b"}])
    arrow = next(e for e in built.elements if e["type"] == "arrow")
    assert len(arrow["points"]) == 2 and arrow["roundness"] is None


def test_lr_layer_gap_grows_so_arrow_labels_fit() -> None:
    label = "enqueue the job asynchronously"
    built = sc.build_elements([
        {"id": "a", "type": "rectangle", "label": "A"}, {"id": "b", "type": "rectangle", "label": "B"},
        {"type": "arrow", "start": "a", "end": "b", "label": label}], direction="LR")
    arrow = next(e for e in built.elements if e["type"] == "arrow")
    text = next(e for e in built.elements if e["type"] == "text" and e["containerId"] == arrow["id"])
    assert text["width"] <= arrow["width"], "label wider than the arrow it sits on"
