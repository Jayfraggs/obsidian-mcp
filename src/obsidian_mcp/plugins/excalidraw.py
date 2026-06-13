"""ExcalidrawService – generate and manipulate Excalidraw diagram notes.

Produces ``.excalidraw.md`` files that Obsidian's Excalidraw plugin can
open and edit.  All generation is static markdown — no Excalidraw instance
required.

Element ID scheme: deterministic short IDs derived from position in the
element list, making diffs readable and stable across re-generation.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any

from obsidian_mcp.vault.service import VaultService

# ── Excalidraw file constants ────────────────────────────────────────
_EX_VERSION = 2
_EX_SOURCE = "obsidian-mcp"
_EX_APP_STATE: dict[str, Any] = {
    "viewBackgroundColor": "transparent",
    "gridSize": None,
}

# Default style values
_DEFAULT_FILL = "hachure"
_DEFAULT_STROKE = "#1e1e1e"
_DEFAULT_BG = "transparent"
_DEFAULT_FONT = 3       # Excalidraw font: 1=hand, 2=normal, 3=mono
_DEFAULT_FONT_SIZE = 16
_BOX_W = 180
_BOX_H = 60
_GAP_X = 80
_GAP_Y = 80


@dataclass
class ExElement:
    """A single Excalidraw drawable element."""
    id: str
    type: str            # rectangle, ellipse, arrow, text, line
    x: float
    y: float
    width: float
    height: float
    angle: float = 0.0
    strokeColor: str = _DEFAULT_STROKE
    backgroundColor: str = _DEFAULT_BG
    fillStyle: str = _DEFAULT_FILL
    strokeWidth: int = 2
    strokeStyle: str = "solid"
    roughness: int = 1
    opacity: int = 100
    text: str = ""
    fontSize: int = _DEFAULT_FONT_SIZE
    fontFamily: int = _DEFAULT_FONT
    textAlign: str = "center"
    verticalAlign: str = "middle"
    # Arrow-specific
    startBinding: dict[str, Any] | None = None
    endBinding: dict[str, Any] | None = None
    points: list[list[float]] = field(default_factory=lambda: [[0, 0], [1, 0]])

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Remove arrow fields from non-arrow elements
        if self.type not in ("arrow", "line"):
            del d["startBinding"]
            del d["endBinding"]
            del d["points"]
        # Remove text fields from non-text elements
        if self.type not in ("text", "rectangle", "ellipse"):
            for k in ("text", "fontSize", "fontFamily", "textAlign", "verticalAlign"):
                d.pop(k, None)
        return d


class ExcalidrawService:
    """Generate Excalidraw architecture and concept diagrams."""

    def __init__(self, vault: VaultService) -> None:
        self._vault = vault

    # ------------------------------------------------------------------ #
    # High-level diagram generators
    # ------------------------------------------------------------------ #

    def generate_architecture(
        self,
        path: str,
        title: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, str]],
        *,
        layout: str = "layered",
    ) -> dict[str, Any]:
        """Generate an architecture diagram from an explicit node/edge spec.

        Parameters
        ----------
        nodes:
            List of ``{"id": str, "label": str, "type": str}`` dicts.
            ``type`` is one of ``service``, ``database``, ``queue``,
            ``external``, ``user`` — controls shape/style.
        edges:
            List of ``{"from": str, "to": str, "label": str | None}``.
        layout:
            ``layered`` (left-to-right), ``grid``, or ``radial``.
        """
        positions = _layout_nodes(nodes, layout)
        elements: list[ExElement] = []
        id_counter = [0]

        node_center: dict[str, tuple[float, float]] = {}

        for node in nodes:
            nid = node["id"]
            pos = positions.get(nid, (0.0, 0.0))
            x, y = pos
            shape, bg = _node_style(node.get("type", "service"))
            elem = self._make_node_element(
                _next_id(id_counter), shape, x, y,
                node.get("label", nid), bg
            )
            elements.append(elem)
            node_center[nid] = (x + _BOX_W / 2, y + _BOX_H / 2)

        for edge in edges:
            src = node_center.get(edge["from"])
            dst = node_center.get(edge["to"])
            if src is None or dst is None:
                continue
            arrow = self._make_arrow(
                _next_id(id_counter), src, dst,
                label=edge.get("label", ""),
            )
            elements.append(arrow)

        output_path = path if path.endswith(".excalidraw.md") else f"{path}.excalidraw.md"
        content = _build_excalidraw_md(title, elements)
        return self._vault.create_note(output_path, content)

    def generate_concept_map(
        self,
        path: str,
        central_concept: str,
        branches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate a radial concept map centred on one idea.

        Parameters
        ----------
        branches:
            List of ``{"label": str, "children": list[str]}``.
            Each branch becomes a second-level node; its children are
            third-level leaf nodes.
        """
        elements: list[ExElement] = []
        id_counter = [0]

        cx, cy = 400.0, 300.0
        # Central node
        elements.append(self._make_node_element(
            _next_id(id_counter), "ellipse",
            cx - _BOX_W / 2, cy - _BOX_H / 2,
            central_concept, "#fff3bf",
        ))
        center_pos = (cx, cy)

        branch_count = len(branches)
        for b_idx, branch in enumerate(branches):
            angle = (2 * math.pi * b_idx) / max(branch_count, 1)
            bx = cx + math.cos(angle) * 280 - _BOX_W / 2
            by = cy + math.sin(angle) * 200 - _BOX_H / 2
            branch_id = _next_id(id_counter)
            elements.append(self._make_node_element(
                branch_id, "rectangle", bx, by,
                branch["label"], "#dbe9ff",
            ))
            branch_center = (bx + _BOX_W / 2, by + _BOX_H / 2)
            elements.append(self._make_arrow(_next_id(id_counter), center_pos, branch_center))

            children: list[str] = branch.get("children", [])
            for c_idx, child_label in enumerate(children):
                offset = (c_idx - len(children) / 2) * 100
                perp_angle = angle + math.pi / 2
                lx = branch_center[0] + math.cos(angle) * 200 + math.cos(perp_angle) * offset - _BOX_W / 2
                ly = branch_center[1] + math.sin(angle) * 160 + math.sin(perp_angle) * offset - _BOX_H / 2 + 20
                leaf_id = _next_id(id_counter)
                elements.append(self._make_node_element(
                    leaf_id, "rectangle", lx, ly, child_label, "#f0fff0"
                ))
                leaf_center = (lx + _BOX_W / 2, ly + _BOX_H / 2)
                elements.append(self._make_arrow(_next_id(id_counter), branch_center, leaf_center))

        output_path = path if path.endswith(".excalidraw.md") else f"{path}.excalidraw.md"
        content = _build_excalidraw_md(central_concept, elements)
        return self._vault.create_note(output_path, content)

    def parse_elements(self, path: str) -> dict[str, Any]:
        """Parse and return the element list from an existing Excalidraw note."""
        note = self._vault.read_note(path)
        payload = _extract_json_payload(note["content"])
        if payload is None:
            return {"path": path, "elements": [], "error": "No valid Excalidraw JSON found."}
        return {
            "path": path,
            "element_count": len(payload.get("elements", [])),
            "elements": payload.get("elements", []),
        }

    def add_text_annotation(
        self,
        path: str,
        text: str,
        *,
        x: float = 40.0,
        y: float = 40.0,
    ) -> dict[str, Any]:
        """Add a floating text element to an existing Excalidraw note."""
        note = self._vault.read_note(path)
        payload = _extract_json_payload(note["content"])
        if payload is None:
            return {"path": path, "error": "No valid Excalidraw JSON found."}

        elements = payload.get("elements", [])
        new_id = f"text-{len(elements):04d}"
        elements.append({
            "id": new_id, "type": "text",
            "x": x, "y": y, "width": 200, "height": 30,
            "angle": 0, "strokeColor": _DEFAULT_STROKE,
            "backgroundColor": "transparent", "fillStyle": "hachure",
            "strokeWidth": 1, "strokeStyle": "solid", "roughness": 0,
            "opacity": 100, "text": text,
            "fontSize": _DEFAULT_FONT_SIZE, "fontFamily": _DEFAULT_FONT,
            "textAlign": "left", "verticalAlign": "top",
        })
        payload["elements"] = elements
        new_content = _rebuild_excalidraw_md(note["content"], payload)
        return self._vault.update_note(path, new_content)

    # ------------------------------------------------------------------ #
    # Element factory helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _make_node_element(
        eid: str, shape: str, x: float, y: float,
        label: str, bg_color: str,
    ) -> ExElement:
        return ExElement(
            id=eid, type=shape,
            x=x, y=y, width=_BOX_W, height=_BOX_H,
            backgroundColor=bg_color,
            fillStyle="solid",
            text=label,
        )

    @staticmethod
    def _make_arrow(
        eid: str,
        src: tuple[float, float],
        dst: tuple[float, float],
        *,
        label: str = "",
    ) -> ExElement:
        dx = dst[0] - src[0]
        dy = dst[1] - src[1]
        return ExElement(
            id=eid, type="arrow",
            x=src[0], y=src[1],
            width=abs(dx), height=abs(dy),
            points=[[0, 0], [dx, dy]],
            text=label,
            strokeStyle="solid",
            roughness=0,
        )


# ── Layout algorithms ──────────────────────────────────────────────────

def _layout_nodes(
    nodes: list[dict[str, Any]],
    layout: str,
) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}
    n = len(nodes)
    if layout == "radial":
        cx, cy = 400.0, 300.0
        for i, node in enumerate(nodes):
            angle = (2 * math.pi * i) / max(n, 1)
            x = cx + math.cos(angle) * 260 - _BOX_W / 2
            y = cy + math.sin(angle) * 180 - _BOX_H / 2
            positions[node["id"]] = (x, y)
    elif layout == "grid":
        cols = math.ceil(math.sqrt(n))
        for i, node in enumerate(nodes):
            col = i % cols
            row = i // cols
            positions[node["id"]] = (
                60.0 + col * (_BOX_W + _GAP_X),
                60.0 + row * (_BOX_H + _GAP_Y),
            )
    else:  # layered (left-to-right)
        for i, node in enumerate(nodes):
            positions[node["id"]] = (
                60.0 + i * (_BOX_W + _GAP_X),
                120.0,
            )
    return positions


def _node_style(node_type: str) -> tuple[str, str]:
    """Return (shape, bg_color) for a node type."""
    return {
        "service":  ("rectangle", "#dbe9ff"),
        "database": ("ellipse",   "#fce8ff"),
        "queue":    ("rectangle", "#fff3bf"),
        "external": ("rectangle", "#e8f5e9"),
        "user":     ("ellipse",   "#ffeedd"),
    }.get(node_type, ("rectangle", "transparent"))


# ── JSON payload helpers ───────────────────────────────────────────────

def _build_excalidraw_md(title: str, elements: list[ExElement]) -> str:
    payload = {
        "type": "excalidraw",
        "version": _EX_VERSION,
        "source": _EX_SOURCE,
        "elements": [e.to_dict() for e in elements],
        "appState": _EX_APP_STATE,
    }
    return (
        "---\n"
        "excalidraw-plugin: parsed\n"
        f"title: {title}\n"
        "tags: [excalidraw, diagram]\n"
        "---\n\n"
        f"# {title}\n\n"
        "```json\n"
        f"{json.dumps(payload, indent=2, sort_keys=True)}\n"
        "```\n"
    )


def _extract_json_payload(content: str) -> dict[str, Any] | None:
    import re
    m = re.search(r"```json\s*\n([\s\S]+?)\n```", content)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _rebuild_excalidraw_md(original: str, payload: dict[str, Any]) -> str:
    import re
    new_json = f"```json\n{json.dumps(payload, indent=2, sort_keys=True)}\n```"
    return re.sub(r"```json\s*\n[\s\S]+?\n```", new_json, original, count=1)


def _next_id(counter: list[int]) -> str:
    idx = counter[0]
    counter[0] += 1
    return f"el-{idx:04d}"
