"""ExcalidrawService – generate and manipulate Excalidraw diagram notes.

Produces ``.excalidraw.md`` files that Obsidian's Excalidraw plugin can
open and edit.  All generation is static markdown — no Excalidraw instance
required.

Element ID scheme: deterministic short IDs derived from position in the
element list, making diffs readable and stable across re-generation.

File format
-----------
The plugin's ``parsed`` mode requires:

    ---
    excalidraw-plugin: parsed
    ...
    ---

    # Title

    %%
    ## Drawing
    ```json
    { ...scene JSON... }
    ```
    %%

The JSON block MUST be inside ``%%...%%`` Obsidian comment delimiters.
A bare fenced code block is silently ignored by the plugin.

Bound arrows
------------
Excalidraw elements use bidirectional references so that moving a node
also moves its connected arrows.  Every shape carries a ``boundElements``
list and every arrow carries ``startBinding`` / ``endBinding`` dicts.
Without these the diagram looks correct but arrows detach on drag.

Script Engine integration
-------------------------
``write_ea_script`` deposits a JavaScript ``.md`` file into the vault's
Excalidraw scripts folder (default ``Excalidraw/Scripts/``).  Obsidian
picks it up automatically and exposes it via the command palette.  The MCP
cannot *run* scripts, but the AI can *author* them for the user to trigger.

Embedding
---------
``embed_in_note`` inserts an ``![[path]]`` transclusion into any markdown
note so the diagram appears inline.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from pathlib import Path

from obsidian_mcp.vault.service import VaultService

# Directory containing bundled Script Engine .md files
_SCRIPTS_DIR = Path(__file__).parent / "ea_scripts"

# Catalogue of bundled scripts: name → short description
# Used by install_scripts() and the MCP tool docstring.
BUNDLED_SCRIPTS: dict[str, str] = {
    "Auto Layout":
        "Automatic ELK-powered layout for selected elements (layered, radial, tree). "
        "Requires internet on first run to load elkjs.",
    "Connect elements":
        "Connect two selected objects with a bound arrow. "
        "Respects existing groups and matches source element style.",
    "Box Selected Elements":
        "Wrap all selected elements in an enclosing rectangle. "
        "Prompts for padding; groups the box with the selection.",
    "Box Each Selected Groups":
        "Add an individual bounding box around each selected group separately.",
    "Add Next Step in Process":
        "Prompt for a label, create a sticky-note step, and auto-connect it "
        "with an arrow from the currently selected element.",
    "Mindmap Builder":
        "Full interactive mindmap environment with keyboard shortcuts, "
        "auto-layout, recursive grouping, and contrast-aware colouring. "
        "Opens in the Obsidian sidepanel.",
    "Mindmap format":
        "Auto-format a left-to-right mindmap: re-space nodes, align branches, "
        "sort children by arrow creation time.",
    "Mindmap connector":
        "Connect selected elements with mindmap-style right-angle lines "
        "(right and down only). Ordered by element creation time.",
    "Set Dimensions":
        "Prompt for exact x, y, width, height values and apply them to "
        "the largest selected element.",
    "Elbow connectors":
        "Convert selected arrows/lines to right-angle elbow connectors. "
        "Optionally centres the connect points.",
    "Concatenate lines":
        "Merge two selected arrows or lines into one, inheriting the style "
        "of the topmost element.",
    "Convert freedraw to line":
        "Convert freehand drawings to editable polylines. "
        "Adjustable point density in script settings.",
    "Convert selected text elements to sticky notes":
        "Convert plain text elements to transparent-background sticky notes "
        "(wrappable format).",
    "Add Link to Existing File and Open":
        "Prompt for a vault file and attach a wikilink to the selected element.",
    "Add Link to New Page and Open":
        "Prompt for a filename, create a new note or drawing, "
        "and attach a link to the selected element.",
    "Deconstruct selected elements into new drawing":
        "Move selected elements into a new Excalidraw file and replace them "
        "with an embedded reference in the original drawing.",
    "Copy Selected Element Styles to Global":
        "Copy the stroke/fill/font style of the selected element to the "
        "global Excalidraw toolbar state.",
    "Add Connector Point":
        "Add a small bullet-point circle to the top-left of each selected "
        "text element and group them together.",
}

# ── Excalidraw file constants ──────────────────────────────────────────
_EX_VERSION = 2
_EX_SOURCE = "obsidian-mcp"
_EX_APP_STATE: dict[str, Any] = {
    "viewBackgroundColor": "transparent",
    "gridSize": None,
}

# Default style values
_DEFAULT_STROKE = "#1e1e1e"
_DEFAULT_BG = "transparent"
_DEFAULT_FONT = 3       # 1=hand (Virgil), 2=normal (Helvetica), 3=mono (Cascadia)
_DEFAULT_FONT_SIZE = 16
_BOX_W = 180
_BOX_H = 60
_GAP_X = 80
_GAP_Y = 80

# Binding gap: pixels from element edge to arrow endpoint
_BIND_GAP = 8


@dataclass
class ExElement:
    """A single Excalidraw drawable element."""
    id: str
    type: str            # rectangle | ellipse | diamond | arrow | text | line
    x: float
    y: float
    width: float
    height: float
    angle: float = 0.0
    strokeColor: str = _DEFAULT_STROKE
    backgroundColor: str = _DEFAULT_BG
    fillStyle: str = "hachure"
    strokeWidth: int = 2
    strokeStyle: str = "solid"
    roughness: int = 1
    opacity: int = 100
    # Text / label
    text: str = ""
    fontSize: int = _DEFAULT_FONT_SIZE
    fontFamily: int = _DEFAULT_FONT
    textAlign: str = "center"
    verticalAlign: str = "middle"
    # Binding (shapes): arrows that touch this element
    boundElements: list[dict[str, str]] = field(default_factory=list)
    # Arrow-specific
    startBinding: dict[str, Any] | None = None
    endBinding: dict[str, Any] | None = None
    points: list[list[float]] = field(default_factory=lambda: [[0.0, 0.0], [1.0, 0.0]])
    startArrowhead: str | None = None
    endArrowhead: str = "arrow"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        is_arrow = self.type in ("arrow", "line")
        is_shape = self.type in ("rectangle", "ellipse", "diamond")
        is_text  = self.type == "text"

        if not is_arrow:
            for k in ("startBinding", "endBinding", "points", "startArrowhead", "endArrowhead"):
                d.pop(k, None)
        if is_arrow:
            # Arrows don't need boundElements (shapes own the binding list)
            d.pop("boundElements", None)
            # Remove None arrowheads from output (cleaner JSON)
            if d.get("startArrowhead") is None:
                d.pop("startArrowhead", None)

        if not (is_shape or is_text):
            for k in ("text", "fontSize", "fontFamily", "textAlign", "verticalAlign"):
                d.pop(k, None)

        if not is_shape:
            d.pop("boundElements", None)

        # Remove empty label text from shapes/arrows to keep JSON tidy
        if d.get("text") == "":
            d.pop("text", None)

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
            ``external``, ``user``, ``container`` — controls shape/style.
        edges:
            List of ``{"from": str, "to": str, "label": str | None}``.
        layout:
            ``layered`` (left-to-right), ``grid``, or ``radial``.
        """
        positions = _layout_nodes(nodes, layout)
        elements: list[ExElement] = []
        id_counter = [0]

        # node_id → (element_id, center_x, center_y)
        node_meta: dict[str, tuple[str, float, float]] = {}

        for node in nodes:
            nid = node["id"]
            pos = positions.get(nid, (0.0, 0.0))
            x, y = pos
            shape, bg = _node_style(node.get("type", "service"))
            eid = _next_id(id_counter)
            elem = _make_node_element(eid, shape, x, y, node.get("label", nid), bg)
            elements.append(elem)
            node_meta[nid] = (eid, x + _BOX_W / 2, y + _BOX_H / 2)

        for edge in edges:
            src_meta = node_meta.get(edge["from"])
            dst_meta = node_meta.get(edge["to"])
            if src_meta is None or dst_meta is None:
                continue
            src_eid, sx, sy = src_meta
            dst_eid, dx, dy = dst_meta
            arrow_eid = _next_id(id_counter)
            arrow = _make_bound_arrow(
                arrow_eid,
                (sx, sy), src_eid,
                (dx, dy), dst_eid,
                label=edge.get("label", ""),
            )
            elements.append(arrow)
            # Register arrow on both endpoint shapes
            _bind_arrow_to_element(elements, src_eid, arrow_eid, "start")
            _bind_arrow_to_element(elements, dst_eid, arrow_eid, "end")

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
        center_eid = _next_id(id_counter)
        elements.append(_make_node_element(
            center_eid, "ellipse",
            cx - _BOX_W / 2, cy - _BOX_H / 2,
            central_concept, "#fff3bf",
        ))

        branch_count = len(branches)
        for b_idx, branch in enumerate(branches):
            angle = (2 * math.pi * b_idx) / max(branch_count, 1)
            bx = cx + math.cos(angle) * 280 - _BOX_W / 2
            by = cy + math.sin(angle) * 200 - _BOX_H / 2
            branch_eid = _next_id(id_counter)
            elements.append(_make_node_element(
                branch_eid, "rectangle", bx, by,
                branch["label"], "#dbe9ff",
            ))
            branch_center = (bx + _BOX_W / 2, by + _BOX_H / 2)

            arrow_eid = _next_id(id_counter)
            elements.append(_make_bound_arrow(
                arrow_eid,
                (cx, cy), center_eid,
                branch_center, branch_eid,
            ))
            _bind_arrow_to_element(elements, center_eid, arrow_eid, "start")
            _bind_arrow_to_element(elements, branch_eid, arrow_eid, "end")

            children: list[str] = branch.get("children", [])
            for c_idx, child_label in enumerate(children):
                offset = (c_idx - len(children) / 2) * 100
                perp = angle + math.pi / 2
                lx = branch_center[0] + math.cos(angle) * 200 + math.cos(perp) * offset - _BOX_W / 2
                ly = branch_center[1] + math.sin(angle) * 160 + math.sin(perp) * offset - _BOX_H / 2 + 20
                leaf_eid = _next_id(id_counter)
                elements.append(_make_node_element(leaf_eid, "rectangle", lx, ly, child_label, "#f0fff0"))
                leaf_center = (lx + _BOX_W / 2, ly + _BOX_H / 2)
                leaf_arrow_eid = _next_id(id_counter)
                elements.append(_make_bound_arrow(
                    leaf_arrow_eid,
                    branch_center, branch_eid,
                    leaf_center, leaf_eid,
                ))
                _bind_arrow_to_element(elements, branch_eid, leaf_arrow_eid, "start")
                _bind_arrow_to_element(elements, leaf_eid, leaf_arrow_eid, "end")

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

    def install_scripts(
        self,
        *,
        scripts: list[str] | None = None,
        scripts_folder: str = "Excalidraw/Scripts",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Install bundled Excalidraw Script Engine files into the vault.

        Copies the requested scripts (or all bundled scripts if ``scripts``
        is None) from the package's ``ea_scripts/`` directory into the vault's
        script folder.  Obsidian picks them up automatically — no restart
        required.

        Parameters
        ----------
        scripts:
            List of script names to install (without ``.md``).
            Pass None to install all bundled scripts.
            Available names: see BUNDLED_SCRIPTS keys.
        scripts_folder:
            Vault-relative destination folder.  Must match the path set in
            Excalidraw Settings → Script Engine folder.
        overwrite:
            If True, overwrite existing vault notes at the target path.
            Default False — skips scripts that already exist.

        Returns
        -------
        dict with keys:
            installed   — list of script names successfully written
            skipped     — list of names skipped (already exist, overwrite=False)
            not_found   — list of requested names not in the bundle
        """
        requested = scripts if scripts is not None else list(BUNDLED_SCRIPTS.keys())
        installed, skipped, not_found = [], [], []

        for name in requested:
            src = _SCRIPTS_DIR / f"{name}.md"
            if not src.exists():
                not_found.append(name)
                continue

            dest_path = f"{scripts_folder}/{name}.md"
            script_content = src.read_text(encoding="utf-8")

            try:
                existing = self._vault.read_note(dest_path)
                if existing.get("content") and not overwrite:
                    skipped.append(name)
                    continue
                self._vault.update_note(dest_path, script_content)
            except Exception:
                # Note doesn't exist yet — create it
                try:
                    self._vault.create_note(dest_path, script_content)
                except Exception:
                    if overwrite:
                        self._vault.update_note(dest_path, script_content)
                    else:
                        skipped.append(name)
                        continue
            installed.append(name)

        return {
            "installed": installed,
            "skipped": skipped,
            "not_found": not_found,
            "scripts_folder": scripts_folder,
        }

    def list_bundled_scripts(self) -> list[dict[str, str]]:
        """Return the catalogue of scripts bundled with obsidian-mcp.

        Each entry has ``name`` and ``description``.
        Pass name values to ``install_scripts(scripts=[...])`` to install
        a subset.
        """
        return [
            {"name": name, "description": desc}
            for name, desc in BUNDLED_SCRIPTS.items()
        ]

    def write_ea_script(
        self,
        script_name: str,
        description: str,
        js_code: str,
        *,
        scripts_folder: str = "Excalidraw/Scripts",
    ) -> dict[str, Any]:
        """Write a JavaScript Excalidraw Script Engine file to the vault.

        The script appears in Obsidian's command palette as
        "Excalidraw Script: <script_name>" and can be assigned a hotkey.

        The file is stored as a markdown .md note — Obsidian's Script Engine
        accepts .md, plain .txt, or .js; .md is preferred because it renders
        as a readable note and gets indexed by the vault.

        Parameters
        ----------
        script_name:
            Human-readable name shown in the command palette.
        description:
            One-paragraph explanation of what the script does.
            Stored as markdown prose above the code fence.
        js_code:
            Valid JavaScript.  The Script Engine injects two globals:
            ``ea`` (ExcalidrawAutomate, pre-bound to the active view) and
            ``utils`` (inputPrompt, suggester helpers).
        scripts_folder:
            Vault-relative folder.  Must match the path configured in
            Excalidraw Settings → Script Engine folder.
        """
        path = f"{scripts_folder}/{script_name}.md"
        content = (
            f"# {script_name}\n\n"
            f"{description}\n\n"
            "```javascript\n"
            f"{js_code.strip()}\n"
            "```\n"
        )
        return self._vault.create_note(path, content)

    def embed_in_note(
        self,
        drawing_path: str,
        note_path: str,
        *,
        heading: str | None = None,
        width: int | None = None,
    ) -> dict[str, Any]:
        """Insert an Excalidraw transclusion into a markdown note.

        Appends ``![[drawing_path|width]]`` (or under an optional heading)
        to the target note.  If the note does not exist it is created.

        Parameters
        ----------
        drawing_path:
            Vault-relative path of the ``.excalidraw.md`` file.
        note_path:
            Vault-relative path of the markdown note to embed into.
        heading:
            If given, a ``## heading`` is prepended before the embed.
        width:
            Optional pixel width, e.g. ``600``.  Produces ``![[...\\|600]]``.
        """
        # Build the wikilink embed
        link = drawing_path
        if width is not None:
            link = f"{link}|{width}"
        embed_line = f"![[{link}]]"
        if heading:
            embed_line = f"\n## {heading}\n\n{embed_line}"
        else:
            embed_line = f"\n{embed_line}"

        try:
            existing = self._vault.read_note(note_path)
            new_content = existing["content"].rstrip() + "\n" + embed_line + "\n"
            return self._vault.update_note(note_path, new_content)
        except Exception:
            return self._vault.create_note(note_path, embed_line.lstrip() + "\n")


# ── Element factories ──────────────────────────────────────────────────

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
        boundElements=[],   # populated later by _bind_arrow_to_element
    )


def _make_bound_arrow(
    eid: str,
    src: tuple[float, float], src_elem_id: str,
    dst: tuple[float, float], dst_elem_id: str,
    *,
    label: str = "",
) -> ExElement:
    """Create an arrow with proper startBinding/endBinding for drag-attached behaviour."""
    sx, sy = src
    dx, dy = dst
    rel_dx = dx - sx
    rel_dy = dy - sy
    return ExElement(
        id=eid, type="arrow",
        x=sx, y=sy,
        width=abs(rel_dx), height=abs(rel_dy),
        points=[[0.0, 0.0], [rel_dx, rel_dy]],
        text=label,
        strokeStyle="solid",
        roughness=0,
        startBinding={"elementId": src_elem_id, "focus": 0.0, "gap": _BIND_GAP},
        endBinding={"elementId": dst_elem_id, "focus": 0.0, "gap": _BIND_GAP},
        endArrowhead="arrow",
    )


def _bind_arrow_to_element(
    elements: list[ExElement],
    shape_eid: str,
    arrow_eid: str,
    side: str,  # "start" | "end"
) -> None:
    """Append an arrow reference to the shape's boundElements list."""
    for elem in elements:
        if elem.id == shape_eid:
            elem.boundElements.append({"id": arrow_eid, "type": "arrow"})
            return


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
        "service":   ("rectangle", "#dbe9ff"),
        "database":  ("ellipse",   "#fce8ff"),
        "queue":     ("rectangle", "#fff3bf"),
        "external":  ("rectangle", "#e8f5e9"),
        "user":      ("ellipse",   "#ffeedd"),
        "container": ("rectangle", "#f0f0f0"),
    }.get(node_type, ("rectangle", "transparent"))


# ── File format helpers ────────────────────────────────────────────────

def _build_excalidraw_md(title: str, elements: list[ExElement]) -> str:
    """Produce a valid .excalidraw.md file with the %% Drawing block."""
    payload = {
        "type": "excalidraw",
        "version": _EX_VERSION,
        "source": _EX_SOURCE,
        "elements": [e.to_dict() for e in elements],
        "appState": _EX_APP_STATE,
    }
    json_str = json.dumps(payload, indent=2, sort_keys=True)
    # IMPORTANT: the JSON must live inside %%...%% comment delimiters,
    # under the "## Drawing" heading. A bare fenced code block is ignored
    # by the Excalidraw plugin in parsed mode.
    return (
        "---\n"
        "excalidraw-plugin: parsed\n"
        f"title: {title}\n"
        "tags: [excalidraw, diagram]\n"
        "---\n\n"
        f"# {title}\n\n"
        "%%\n"
        "## Drawing\n"
        "```json\n"
        f"{json_str}\n"
        "```\n"
        "%%\n"
    )


def _extract_json_payload(content: str) -> dict[str, Any] | None:
    """Extract the Excalidraw JSON scene from a note's content."""
    # Try %% comment block first (parsed mode), then bare code block
    m = re.search(r"%%.*?```json\s*\n([\s\S]+?)\n```.*?%%", content, re.DOTALL)
    if not m:
        m = re.search(r"```json\s*\n([\s\S]+?)\n```", content)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _rebuild_excalidraw_md(original: str, payload: dict[str, Any]) -> str:
    """Replace the JSON block inside a %%...%% section, or bare if absent."""
    new_json_block = f"```json\n{json.dumps(payload, indent=2, sort_keys=True)}\n```"
    # Try to replace inside %% block
    replaced = re.sub(
        r"(%%.*?)```json\s*\n[\s\S]+?\n```(.*?%%)",
        lambda m: m.group(1) + new_json_block + m.group(2),
        original, count=1, flags=re.DOTALL,
    )
    if replaced != original:
        return replaced
    # Fallback: replace bare code block
    return re.sub(r"```json\s*\n[\s\S]+?\n```", new_json_block, original, count=1)


def _next_id(counter: list[int]) -> str:
    idx = counter[0]
    counter[0] += 1
    return f"el-{idx:04d}"
