"""ExcalidrawService – generate, validate and edit Excalidraw diagram notes.

Produces ``.excalidraw.md`` files that Obsidian's Excalidraw plugin opens
natively.  All the hard parts (bound labels, two-way arrow bindings, relative
arrow points, 8-char text ids, the ``## Text Elements`` section, compressed
drawings) live in :mod:`obsidian_mcp.plugins.excalidraw_scene`; this service is
the vault-facing layer on top of it.

Design rule: **the LLM never writes scene JSON.**  It writes a small
*skeleton* (nodes + arrows, optional coordinates) and the engine produces a
complete, valid scene.  If a client writes ``.excalidraw.md`` through the
generic note tools anyway, :meth:`ExcalidrawService.write_raw` validates and
repairs it (or rejects it with an actionable message) instead of letting a
broken drawing land in the vault.

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

import math
from pathlib import Path
from typing import Any

from obsidian_mcp.errors import NoteNotFoundError
from obsidian_mcp.plugins import excalidraw_scene as sc
from obsidian_mcp.vault.service import VaultService

DRAWING_SUFFIX = ".excalidraw.md"


def is_drawing_path(path: str) -> bool:
    """True for paths the Obsidian Excalidraw plugin treats as drawings."""
    return path.lower().endswith(DRAWING_SUFFIX)


GUIDANCE = (
    "Do not hand-write .excalidraw.md JSON. Call excalidraw_get_schema, then "
    "excalidraw_create_diagram (any diagram), excalidraw_generate_flowchart, "
    "excalidraw_generate_architecture or excalidraw_generate_concept_map; "
    "use excalidraw_edit_diagram to change an existing drawing."
)

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



def _fail(error: str, problems: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"ok": False, "written": False, "error": error}
    if problems:
        out["problems"] = problems
    out["hint"] = GUIDANCE
    out.update(extra)
    return out


def _slim(res: dict[str, Any]) -> dict[str, Any]:
    """Drop the echoed file body — a drawing's JSON is large and the caller never needs it back."""
    res.pop("content", None)
    return res


def _out_path(path: str) -> str:
    return path if is_drawing_path(path) else f"{path}{DRAWING_SUFFIX}"


def _direction(value: str) -> str:
    return "LR" if str(value).upper() in ("LR", "RL", "HORIZONTAL", "LEFT-TO-RIGHT") else "TB"


SCHEMA: dict[str, Any] = {
    "rule": (
        "Never write .excalidraw.md JSON yourself. Describe the diagram as `elements` "
        "(nodes + arrows) and let the server build the scene. Coordinates are optional: "
        "omit x/y and shapes are laid out automatically following the arrows."
    ),
    "tools": {
        "excalidraw_create_diagram": "Any diagram from an `elements` list (this schema).",
        "excalidraw_generate_flowchart": "Flowcharts: steps with `next` links; start/decision shapes handled for you.",
        "excalidraw_generate_architecture": "Typed nodes (service/database/queue/…) + edges.",
        "excalidraw_generate_concept_map": "Radial map: centre + branches + leaves.",
        "excalidraw_edit_diagram": "Add/remove/relabel/restyle elements in an existing drawing.",
        "excalidraw_validate": "Check (and optionally repair) any existing drawing.",
    },
    "element_types": {
        "rectangle | ellipse | diamond": {
            "id": "your handle, e.g. 'api' (referenced by arrows)",
            "label": "text shown inside the shape (long labels wrap automatically)",
            "x, y, width, height": "optional; omit for auto layout/size",
            "style (optional)": "backgroundColor, strokeColor, strokeStyle(solid|dashed|dotted), strokeWidth, fontSize",
        },
        "text": {"text": "free-standing text", "x, y": "optional", "fontSize": "optional"},
        "arrow | line": {
            "start": "node id (or {\"x\":..,\"y\":..} for a free end)",
            "end": "node id (or {\"x\":..,\"y\":..})",
            "label": "optional text on the arrow",
            "style (optional)": "strokeStyle, strokeColor, startArrowhead, endArrowhead",
        },
    },
    "example": [
        {"id": "user", "type": "ellipse", "label": "User", "backgroundColor": "#ffeedd"},
        {"id": "api", "type": "rectangle", "label": "API Gateway", "backgroundColor": "#dbe9ff"},
        {"id": "db", "type": "ellipse", "label": "Postgres", "backgroundColor": "#fce8ff"},
        {"type": "arrow", "start": "user", "end": "api", "label": "HTTPS"},
        {"type": "arrow", "start": "api", "end": "db", "label": "SQL"},
    ],
    "colors": {"blue": "#dbe9ff", "yellow": "#fff3bf", "green": "#e8f5e9", "purple": "#fce8ff",
               "orange": "#ffeedd", "grey": "#f0f0f0"},
    "tips": [
        "Reference nodes by the `id` you gave them; unknown ids are reported with the list of known ids.",
        "`from`/`to` work as aliases for `start`/`end`; `text` works as an alias for `label`.",
        "After creating, call excalidraw_embed_in_note to show it inline in a note.",
        "To inspect an existing drawing use excalidraw_parse_elements(compact=true).",
    ],
}


class ExcalidrawService:
    """Generate, validate and edit Excalidraw diagram notes."""

    def __init__(self, vault: VaultService) -> None:
        self._vault = vault

    # ------------------------------------------------------------------ #
    # Schema / guidance
    # ------------------------------------------------------------------ #

    def get_schema(self) -> dict[str, Any]:
        """Return the skeleton format, an example and usage rules."""
        return SCHEMA

    # ------------------------------------------------------------------ #
    # Creation
    # ------------------------------------------------------------------ #

    def _write_new(self, path: str, title: str, payload: dict[str, Any], *,
                   overwrite: bool = False) -> dict[str, Any]:
        out = _out_path(path)
        content = sc.build_drawing_file(title, payload)
        if overwrite:
            try:
                return self._vault.update_note(out, content)
            except NoteNotFoundError:
                pass
        return self._vault.create_note(out, content)

    def _finish(self, path: str, title: str, built: sc.BuildResult, *,
                overwrite: bool = False) -> dict[str, Any]:
        payload = sc.scene_payload(built.elements)
        problems = [i for i in sc.validate_scene(payload) if i.severity == "error"]
        if problems:   # defensive: the engine should never produce these
            return _fail("Internal error: generated scene failed validation",
                         [i.message for i in problems])
        res = _slim(self._write_new(path, title, payload, overwrite=overwrite))
        res.update(ok=True, element_count=len(built.elements), ids=built.ids,
                   warnings=built.warnings)
        return res

    def create_diagram(
        self,
        path: str,
        title: str,
        elements: list[dict[str, Any]],
        *,
        direction: str = "TB",
        layout: str = "layered",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a drawing from a skeleton (see :meth:`get_schema`)."""
        if not isinstance(elements, list) or not elements:
            return _fail("`elements` must be a non-empty list. See excalidraw_get_schema.")
        try:
            built = sc.build_elements(elements, direction=_direction(direction),
                                      layout=layout, origin=(60.0, 60.0))
        except sc.SkeletonError as exc:
            return _fail("Invalid elements — nothing was written. Fix these and retry:", exc.problems)
        return self._finish(path, title, built, overwrite=overwrite)

    def generate_flowchart(
        self,
        path: str,
        title: str,
        steps: list[dict[str, Any]],
        *,
        direction: str = "TB",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Create a flowchart from steps with ``next`` links.

        Each step: ``{"id", "label", "type": start|end|process|decision, "next": [id | {"to", "label"}]}``.
        ``start``/``end`` → ellipse, ``decision`` → diamond, ``process`` → rectangle.
        """
        shape_for = {"start": ("ellipse", "#e8f5e9"), "end": ("ellipse", "#ffeedd"),
                     "process": ("rectangle", "#dbe9ff"), "decision": ("diamond", "#fff3bf"),
                     "io": ("rectangle", "#fce8ff")}
        problems: list[str] = []
        skeleton: list[dict[str, Any]] = []
        arrows: list[dict[str, Any]] = []
        for i, step in enumerate(steps or []):
            if not isinstance(step, dict) or "id" not in step:
                problems.append(f"steps[{i}]: needs an object with an 'id'")
                continue
            sid = str(step["id"])
            kind = str(step.get("type", "process")).lower()
            if kind not in shape_for:
                problems.append(f"steps[{i}] ({sid}): type {kind!r} must be one of {', '.join(shape_for)}")
                continue
            shp, bg = shape_for[kind]
            skeleton.append({"id": sid, "type": shp, "label": str(step.get("label", sid)),
                             "backgroundColor": bg})
            nxt = step.get("next", [])
            if isinstance(nxt, (str, dict)):
                nxt = [nxt]
            for n in nxt or []:
                if isinstance(n, dict):
                    to, lab = n.get("to", n.get("id")), n.get("label")
                else:
                    to, lab = n, None
                if to is None:
                    problems.append(f"steps[{i}] ({sid}): a 'next' entry has no target")
                    continue
                arr: dict[str, Any] = {"type": "arrow", "start": sid, "end": str(to)}
                if lab:
                    arr["label"] = str(lab)
                arrows.append(arr)
        if problems:
            return _fail("Invalid steps — nothing was written. Fix these and retry:", problems)
        if not skeleton:
            return _fail("`steps` must be a non-empty list.")
        try:
            built = sc.build_elements(skeleton + arrows, direction=_direction(direction),
                                      origin=(60.0, 60.0))
        except sc.SkeletonError as exc:
            return _fail("Invalid steps — nothing was written. Fix these and retry:", exc.problems)
        return self._finish(path, title, built, overwrite=overwrite)

    def generate_architecture(
        self,
        path: str,
        title: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, str]],
        *,
        layout: str = "layered",
        overwrite: bool = False,
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
            ``layered`` (left-to-right, follows the edges), ``grid``, or ``radial``.
        """
        problems: list[str] = []
        skeleton: list[dict[str, Any]] = []
        warnings: list[str] = []
        for i, node in enumerate(nodes or []):
            if not isinstance(node, dict) or "id" not in node:
                problems.append(f"nodes[{i}]: needs an object with an 'id'")
                continue
            nid = str(node["id"])
            ntype = node.get("type", "service")
            if ntype not in ("service", "database", "queue", "external", "user", "container"):
                warnings.append(f"node {nid}: unknown type {ntype!r}, drawn as a plain rectangle")
            shape, bg = _node_style(ntype)
            skeleton.append({"id": nid, "type": shape, "label": str(node.get("label", nid)),
                             "backgroundColor": bg})
        for i, edge in enumerate(edges or []):
            if not isinstance(edge, dict):
                problems.append(f"edges[{i}]: must be an object with 'from' and 'to'")
                continue
            src = edge.get("from", edge.get("source"))
            dst = edge.get("to", edge.get("target"))
            if src is None or dst is None:
                problems.append(f"edges[{i}]: needs both 'from' and 'to'")
                continue
            arr: dict[str, Any] = {"type": "arrow", "start": str(src), "end": str(dst)}
            if edge.get("label"):
                arr["label"] = str(edge["label"])
            skeleton.append(arr)
        if problems:
            return _fail("Invalid nodes/edges — nothing was written. Fix these and retry:", problems)
        if not nodes:
            return _fail("`nodes` must be a non-empty list.")
        try:
            built = sc.build_elements(
                skeleton, direction="LR",
                layout=layout if layout in ("grid", "radial") else "layered",
                origin=(60.0, 60.0),
            )
        except sc.SkeletonError as exc:
            return _fail("Invalid nodes/edges — nothing was written. Fix these and retry:", exc.problems)
        built.warnings.extend(warnings)
        return self._finish(path, title, built, overwrite=overwrite)

    def generate_concept_map(
        self,
        path: str,
        central_concept: str,
        branches: list[dict[str, Any]],
        *,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Generate a radial concept map centred on one idea.

        Parameters
        ----------
        branches:
            List of ``{"label": str, "children": list[str]}``.
            Each branch becomes a second-level node; its children are
            third-level leaf nodes.
        """
        problems: list[str] = []
        for i, b in enumerate(branches or []):
            if not isinstance(b, dict) or not b.get("label"):
                problems.append(f"branches[{i}]: needs an object with a 'label'")
        if problems:
            return _fail("Invalid branches — nothing was written. Fix these and retry:", problems)
        if not central_concept or not str(central_concept).strip():
            return _fail("`central_concept` must be non-empty.")

        W, H = 220, 70                      # planning size for branch/leaf boxes
        n = max(len(branches), 1)
        max_kids = max((len(b.get("children", [])) for b in branches), default=0)
        fan = max(max_kids, 1) * (H + 30) + 60
        r_branch = max(320.0, n * fan / (2 * math.pi))
        cx = cy = r_branch + 380.0
        skeleton: list[dict[str, Any]] = [{
            "id": "center", "type": "ellipse", "label": str(central_concept),
            "x": cx - 130, "y": cy - 50, "width": 260, "height": 100,
            "backgroundColor": "#fff3bf",
        }]
        for bi, b in enumerate(branches):
            a = 2 * math.pi * bi / n - math.pi / 2
            ux, uy = math.cos(a), math.sin(a)
            bx, by = cx + ux * r_branch, cy + uy * r_branch
            bid = f"branch{bi}"
            skeleton.append({"id": bid, "type": "rectangle", "label": str(b["label"]),
                             "x": bx - W / 2, "y": by - H / 2, "width": W, "height": H,
                             "backgroundColor": "#dbe9ff"})
            skeleton.append({"type": "arrow", "start": "center", "end": bid})
            kids = [str(c) for c in b.get("children", [])]
            px, py = -uy, ux
            step = abs(px) * (W + 30) + abs(py) * (H + 30)
            for ci, kid in enumerate(kids):
                off = (ci - (len(kids) - 1) / 2) * step
                lx = bx + ux * 280 + px * off
                ly = by + uy * 280 + py * off
                lid = f"branch{bi}_leaf{ci}"
                skeleton.append({"id": lid, "type": "rectangle", "label": kid,
                                 "x": lx - W / 2, "y": ly - H / 2, "width": W, "height": H,
                                 "backgroundColor": "#f0fff0"})
                skeleton.append({"type": "arrow", "start": bid, "end": lid})
        try:
            built = sc.build_elements(skeleton)
        except sc.SkeletonError as exc:   # pragma: no cover - skeleton is generated
            return _fail("Could not build concept map", exc.problems)
        return self._finish(path, str(central_concept), built, overwrite=overwrite)

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #

    def _load(self, path: str) -> tuple[dict[str, Any], sc.ParsedDrawing]:
        note = self._vault.read_note(path)
        return note, sc.parse_drawing(note["content"])

    def parse_elements(self, path: str, *, compact: bool = False) -> dict[str, Any]:
        """Parse and return the element list from an existing Excalidraw note.

        Handles both plain ``json`` and ``compressed-json`` drawings.  With
        ``compact=True`` returns a short nodes/connections summary instead of
        raw elements (far fewer tokens).
        """
        note, parsed = self._load(path)
        if parsed.payload is None:
            return {"path": path, "elements": [], "error": parsed.error or "No valid Excalidraw JSON found."}
        els = parsed.payload.get("elements", [])
        out: dict[str, Any] = {"path": path, "element_count": len(els), "compressed": parsed.compressed}
        if compact:
            out.update(sc.summarize_scene(parsed.payload))
        else:
            out["elements"] = els
        return out

    # ------------------------------------------------------------------ #
    # Validation / repair
    # ------------------------------------------------------------------ #

    def validate_drawing(self, path: str, *, repair: bool = False) -> dict[str, Any]:
        """Check a drawing; with ``repair=True`` fix everything fixable and save."""
        note, parsed = self._load(path)
        if parsed.payload is None:
            return {"path": path, "ok": False, "error": parsed.error, "issues": []}
        issues = sc.validate_scene(parsed.payload)
        result: dict[str, Any] = {"path": path, "repaired": False}
        if repair and issues:
            fixed, changes = sc.repair_scene(parsed.payload)
            self._vault.update_note(path, sc.rewrite_drawing_file(note["content"], fixed))
            result.update(repaired=True, changes=changes)
            issues = sc.validate_scene(fixed)
        result["issues"] = [i.to_dict() for i in issues]
        result["ok"] = not any(i.severity == "error" for i in issues)
        return result

    # ------------------------------------------------------------------ #
    # Editing
    # ------------------------------------------------------------------ #

    def edit_diagram(
        self,
        path: str,
        *,
        add: list[dict[str, Any]] | None = None,
        remove_ids: list[str] | None = None,
        update: dict[str, dict[str, Any]] | None = None,
        direction: str = "TB",
    ) -> dict[str, Any]:
        """Add / remove / relabel / restyle elements in an existing drawing.

        ``add``        skeleton items (see :meth:`get_schema`); arrows may reference
                       existing elements by id or handle.  Unpositioned new shapes are
                       placed in a block below the existing content.
        ``remove_ids`` ids/handles to delete — their labels and any arrows attached to
                       them are removed too.
        ``update``     ``{id_or_handle: {"label": "...", "backgroundColor": "...", ...}}``
        """
        note, parsed = self._load(path)
        if parsed.payload is None:
            return _fail(parsed.error or "Not a readable drawing", path=path)
        try:
            payload, repairs = sc.repair_scene(parsed.payload)
        except ValueError as exc:
            return _fail(str(exc), path=path)
        els: list[dict[str, Any]] = payload["elements"]

        def lookup() -> dict[str, dict[str, Any]]:
            m: dict[str, dict[str, Any]] = {}
            for e in els:
                m[e["id"]] = e
            for e in els:
                h = (e.get("customData") or {}).get("handle")
                if isinstance(h, str):
                    m.setdefault(h, e)
            return m

        problems: list[str] = []
        removed: list[str] = []

        # ── remove ──────────────────────────────────────────────
        if remove_ids:
            look = lookup()
            doomed: set[str] = set()
            for ref in remove_ids:
                tgt = look.get(ref)
                if tgt is None:
                    problems.append(f"remove_ids: {ref!r} not found")
                else:
                    doomed.add(tgt["id"])
            changed = True
            while changed:                      # cascade: labels + attached arrows
                changed = False
                for e in els:
                    if e["id"] in doomed:
                        continue
                    attached = (e.get("containerId") in doomed) or any(
                        isinstance(e.get(s), dict) and e[s].get("elementId") in doomed
                        for s in ("startBinding", "endBinding"))
                    if attached:
                        doomed.add(e["id"])
                        changed = True
            removed = sorted(doomed)
            els[:] = [e for e in els if e["id"] not in doomed]
            for e in els:
                if isinstance(e.get("boundElements"), list):
                    e["boundElements"] = [r for r in e["boundElements"]
                                          if not (isinstance(r, dict) and r.get("id") in doomed)]

        # ── update ──────────────────────────────────────────────
        if update:
            look = lookup()
            allowed = set(sc._STYLE_KEYS) | {"label"}
            for ref, changes in update.items():
                tgt = look.get(ref)
                if tgt is None:
                    problems.append(f"update: {ref!r} not found")
                    continue
                if not isinstance(changes, dict):
                    problems.append(f"update[{ref!r}]: must be an object")
                    continue
                bad = [k for k in changes if k not in allowed]
                if bad:
                    problems.append(f"update[{ref!r}]: unsupported keys {bad}; allowed: {sorted(allowed)}")
                    continue
                for k, v in changes.items():
                    if k == "label":
                        if tgt["type"] == "text":
                            tgt["text"] = tgt["originalText"] = str(v)
                            tgt["width"], tgt["height"] = sc.measure_text(str(v), tgt.get("fontSize", 16))
                        else:
                            sc.set_label(els, tgt, str(v))
                    else:
                        tgt[k] = v
                tgt["version"] = tgt.get("version", 1) + 1

        # ── add ─────────────────────────────────────────────────
        ids: dict[str, str] = {}
        warnings: list[str] = []
        if add:
            bb = sc.bounds(els)
            origin = (bb[0], bb[3] + sc.GAP_MAIN) if bb else (60.0, 60.0)
            try:
                built = sc.build_elements(add, existing=els, direction=_direction(direction),
                                          origin=origin)
                els.extend(built.elements)
                ids, warnings = built.ids, built.warnings
            except sc.SkeletonError as exc:
                problems.extend(exc.problems)

        if problems:
            return _fail("Edit rejected — nothing was written. Fix these and retry:", problems, path=path)

        errs = [i for i in sc.validate_scene(payload) if i.severity == "error"]
        if errs:
            return _fail("Edit would leave the drawing invalid — nothing was written",
                         [i.message for i in errs], path=path)
        res = _slim(self._vault.update_note(path, sc.rewrite_drawing_file(note["content"], payload)))
        res.update(ok=True, ids=ids, removed=removed, warnings=warnings,
                   repaired_before_edit=repairs, element_count=len(els))
        return res

    def add_text_annotation(
        self,
        path: str,
        text: str,
        *,
        x: float = 40.0,
        y: float = 40.0,
    ) -> dict[str, Any]:
        """Add a floating text element to an existing Excalidraw note."""
        note, parsed = self._load(path)
        if parsed.payload is None:
            return {"path": path, "error": parsed.error or "No valid Excalidraw JSON found."}
        payload = parsed.payload
        els = payload.setdefault("elements", [])
        built = sc.build_elements([{"type": "text", "text": text, "x": x, "y": y}], existing=els)
        els.extend(built.elements)
        res = _slim(self._vault.update_note(path, sc.rewrite_drawing_file(note["content"], payload)))
        res.update(ok=True, element_id=built.elements[0]["id"])
        return res

    # ------------------------------------------------------------------ #
    # Guard for generic note tools
    # ------------------------------------------------------------------ #

    def write_raw(self, path: str, content: str, *, mode: str = "create") -> dict[str, Any]:
        """Safely accept ``.excalidraw.md`` content written via ``create_note``/``update_note``.

        The content is parsed, repaired (inline labels → bound text, two-way
        bindings, defaults, …) and re-serialised in the canonical layout.  If it
        cannot be understood, nothing is written and the caller gets guidance.
        """
        parsed = sc.parse_drawing(content)
        if parsed.payload is None:
            return _fail(
                "This is an Excalidraw drawing but its content is not a readable scene — nothing was written. "
                + (parsed.error or ""),
            )
        try:
            fixed, changes = sc.repair_scene(parsed.payload)
        except ValueError as exc:
            return _fail(f"Scene is not valid Excalidraw JSON — nothing was written: {exc}")
        errs = [i for i in sc.validate_scene(fixed) if i.severity == "error"]
        if errs:
            return _fail("Scene still invalid after automatic repair — nothing was written",
                         [f"{i.element_id or ''}: {i.message}".strip(": ") for i in errs])
        if content.strip().startswith("{"):
            stem = Path(path).name[: -len(DRAWING_SUFFIX)] or "Drawing"
            final = sc.build_drawing_file(stem, fixed)
        else:
            final = sc.rewrite_drawing_file(sc.ensure_plugin_frontmatter(content), fixed)
        res = _slim(self._vault.update_note(path, final) if mode == "update"
                    else self._vault.create_note(path, final))
        res.update(
            ok=True, repaired=changes,
            note=("Drawing was written through the generic note tool and normalised. "
                  "Prefer excalidraw_create_diagram / excalidraw_edit_diagram next time."),
        )
        return res

    @staticmethod
    def blocked_edit(op: str) -> dict[str, Any]:
        """Message for ``append_note``/``str_replace_note`` aimed at a drawing."""
        return _fail(
            f"{op} on an Excalidraw drawing would corrupt its JSON — nothing was changed. "
            "Use excalidraw_edit_diagram (add/remove/update elements) or excalidraw_add_annotation."
        )

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
