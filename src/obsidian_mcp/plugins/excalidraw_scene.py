"""Excalidraw scene engine — the one place that knows how to build valid scenes.

Why this module exists
----------------------
LLMs are bad at emitting raw Excalidraw JSON.  A scene that *looks* plausible
is routinely broken in ways Excalidraw silently tolerates or "fixes" by
dropping data:

* ``text`` placed on a rectangle/arrow — Excalidraw ignores it.  Labels must be
  separate ``text`` elements with ``containerId`` pointing at the shape, and the
  shape must list the text in ``boundElements``.
* Arrow bindings that are one-directional (arrow knows the shape, shape does
  not know the arrow) — arrows detach on drag.
* Missing ``seed`` / ``version`` / ``groupIds`` / ``isDeleted`` … fields.
* Arrow ``points`` that are absolute instead of relative to the arrow origin.
* Text element ids that are not 8 characters.  The Obsidian plugin's
  ``## Text Elements`` section keys text by 8-char block ids (medium
  confidence — based on the plugin's file format; we always emit 8 chars).

This module provides:

``build_elements``   skeleton (what an LLM can reliably write) → full elements
``validate_scene``   report problems in any scene
``repair_scene``     fix everything fixable in a raw / LLM-written scene
``parse_drawing``    read ``.excalidraw.md`` (plain *and* ``compressed-json``)
``build_drawing_file`` / ``rewrite_drawing_file``   write canonical files

Nothing here touches the vault; it is pure data-in / data-out.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any

# ── Constants ───────────────────────────────────────────────────────────

EX_VERSION = 2
EX_SOURCE = "obsidian-mcp"
APP_STATE: dict[str, Any] = {"gridSize": None, "viewBackgroundColor": "transparent"}

SHAPE_TYPES = ("rectangle", "ellipse", "diamond")
ARROW_TYPES = ("arrow", "line")
KNOWN_TYPES = SHAPE_TYPES + ARROW_TYPES + (
    "text", "freedraw", "image", "frame", "magicframe", "embeddable", "iframe",
)

DEFAULT_STROKE = "#1e1e1e"
DEFAULT_FONT_FAMILY = 3     # 1 Virgil, 2 Helvetica, 3 Cascadia (mono)
DEFAULT_FONT_SIZE = 16
BOX_W = 180
BOX_H = 60
GAP_MAIN = 80               # between layers
GAP_CROSS = 50              # within a layer
PAD = 16                    # label padding inside a container
BIND_GAP = 8                # px between arrow tip and shape edge
CHAR_W = 0.6                # em-width estimate (exact for mono, safe for others)
LINE_H = 1.25
WRAP_CHARS = 24
ID_LEN = 8

_STYLE_KEYS = (
    "strokeColor", "backgroundColor", "fillStyle", "strokeWidth",
    "strokeStyle", "roughness", "opacity",
)

# ── Errors / small records ──────────────────────────────────────────────


class SkeletonError(ValueError):
    """The skeleton the caller supplied cannot be turned into a scene."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass
class Issue:
    severity: str          # "error" | "warning"
    code: str
    message: str
    element_id: str | None = None
    fixable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity, "code": self.code, "message": self.message,
            "element_id": self.element_id, "fixable": self.fixable,
        }


@dataclass
class BuildResult:
    elements: list[dict[str, Any]]
    ids: dict[str, str]                  # caller handle → element id
    warnings: list[str] = field(default_factory=list)


@dataclass
class ParsedDrawing:
    payload: dict[str, Any] | None
    compressed: bool = False
    error: str | None = None


# ── IDs / numbers ───────────────────────────────────────────────────────

_ID_RE = re.compile(rf"^[A-Za-z0-9]{{{ID_LEN}}}$")


def _r(v: float) -> float:
    out = round(float(v), 2)
    return int(out) if out == int(out) else out


def make_id(seed: str, used: set[str]) -> str:
    """Deterministic 8-char id; bumps a counter on collision."""
    n = 0
    cand = hashlib.sha1(seed.encode()).hexdigest()[:ID_LEN]
    while cand in used:
        n += 1
        cand = hashlib.sha1(f"{seed}#{n}".encode()).hexdigest()[:ID_LEN]
    used.add(cand)
    return cand


def _seed_int(eid: str, salt: str = "") -> int:
    return int(hashlib.sha1((eid + salt).encode()).hexdigest()[:8], 16) & 0x7FFFFFFF


# ── Text metrics ────────────────────────────────────────────────────────


def wrap_label(text: str, width_chars: int = WRAP_CHARS) -> str:
    lines: list[str] = []
    for para in str(text).split("\n"):
        lines.extend(textwrap.wrap(para, width_chars, break_long_words=False) or [""])
    return "\n".join(lines)


def measure_text(text: str, font_size: float = DEFAULT_FONT_SIZE) -> tuple[float, float]:
    lines = str(text).split("\n")
    w = max((len(ln) for ln in lines), default=0) * font_size * CHAR_W
    h = len(lines) * font_size * LINE_H
    return _r(w), _r(h)


# ── Element factories ───────────────────────────────────────────────────


def _common(eid: str, etype: str, x: float, y: float, w: float, h: float,
            **over: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": eid, "type": etype,
        "x": _r(x), "y": _r(y), "width": _r(w), "height": _r(h),
        "angle": 0,
        "strokeColor": DEFAULT_STROKE, "backgroundColor": "transparent",
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 1, "opacity": 100,
        "groupIds": [], "frameId": None, "roundness": None,
        "seed": _seed_int(eid), "version": 1, "versionNonce": _seed_int(eid, "n"),
        "isDeleted": False, "boundElements": [], "updated": 1,
        "link": None, "locked": False,
    }
    d.update(over)
    return d


def _text_element(tid: str, wrapped: str, original: str, x: float, y: float,
                  w: float, h: float, *, font_size: float, font_family: int,
                  container_id: str | None, align: str, valign: str,
                  color: str) -> dict[str, Any]:
    d = _common(tid, "text", x, y, w, h, strokeWidth=1, roughness=0,
                strokeColor=color, boundElements=None)
    d.update(
        text=wrapped, originalText=original, fontSize=font_size,
        fontFamily=font_family, textAlign=align, verticalAlign=valign,
        containerId=container_id, autoResize=True, lineHeight=LINE_H,
    )
    return d


def _label_for_container(container: dict[str, Any], text: str, used: set[str],
                         *, font_size: float = DEFAULT_FONT_SIZE,
                         font_family: int = DEFAULT_FONT_FAMILY,
                         wrap: int | None = None) -> dict[str, Any]:
    """Create the bound text element for *container* and register it."""
    if wrap is None:
        wrap = max(8, int((container["width"] - 2 * PAD) / (font_size * CHAR_W)))
    wrapped = wrap_label(text, wrap)
    tw, th = measure_text(wrapped, font_size)
    cx = container["x"] + container["width"] / 2
    cy = container["y"] + container["height"] / 2
    tid = make_id(container["id"] + ":label", used)
    el = _text_element(
        tid, wrapped, str(text), cx - tw / 2, cy - th / 2, tw, th,
        font_size=font_size, font_family=font_family, container_id=container["id"],
        align="center", valign="middle", color=container.get("strokeColor", DEFAULT_STROKE),
    )
    container.setdefault("boundElements", [])
    if container["boundElements"] is None:
        container["boundElements"] = []
    container["boundElements"].append({"type": "text", "id": tid})
    return el


# ── Geometry ────────────────────────────────────────────────────────────


def _edge_point(shape: dict[str, Any], tx: float, ty: float, gap: float) -> tuple[float, float]:
    """Point on *shape*'s outline facing (tx, ty), pushed out by *gap*."""
    cx = shape["x"] + shape["width"] / 2
    cy = shape["y"] + shape["height"] / 2
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hw, hh = shape["width"] / 2, shape["height"] / 2
    t = shape.get("type")
    if t == "ellipse":
        s = 1.0 / math.sqrt((dx / hw) ** 2 + (dy / hh) ** 2)
    elif t == "diamond":
        s = 1.0 / (abs(dx) / hw + abs(dy) / hh)
    else:
        s = min(hw / abs(dx) if dx else math.inf, hh / abs(dy) if dy else math.inf)
    dist = math.hypot(dx, dy)
    return cx + dx * s + dx / dist * gap, cy + dy * s + dy / dist * gap


# ── Layout ──────────────────────────────────────────────────────────────


def layered_layout(
    ids: list[str],
    edges: list[tuple[str, str]],
    sizes: dict[str, tuple[float, float]],
    direction: str = "TB",
    gap_main: float = GAP_MAIN,
) -> dict[str, tuple[float, float]]:
    """Layered (Sugiyama-lite) layout.  Returns top-left positions.

    Cycles are tolerated (back-edges ignored for layering).  ``direction`` is
    ``"TB"`` (top→bottom) or ``"LR"`` (left→right).
    """
    idset = set(ids)
    succ: dict[str, list[str]] = {i: [] for i in ids}
    pred: dict[str, list[str]] = {i: [] for i in ids}
    seen: set[tuple[str, str]] = set()
    for a, b in edges:
        if a in idset and b in idset and a != b and (a, b) not in seen:
            seen.add((a, b))
            succ[a].append(b)
            pred[b].append(a)

    # Break cycles with an iterative DFS; edges to an in-progress node are back-edges.
    back: set[tuple[str, str]] = set()
    color: dict[str, int] = {}
    roots = [i for i in ids if not pred[i]] + [i for i in ids if pred[i]]
    for root in roots:
        if root in color:
            continue
        color[root] = 1
        stack: list[tuple[str, int]] = [(root, 0)]
        while stack:
            u, k = stack.pop()
            if k < len(succ[u]):
                stack.append((u, k + 1))
                v = succ[u][k]
                if color.get(v) == 1:
                    back.add((u, v))
                elif v not in color:
                    color[v] = 1
                    stack.append((v, 0))
            else:
                color[u] = 2

    dag_pred = {i: [p for p in pred[i] if (p, i) not in back] for i in ids}
    layer: dict[str, int] = {}

    def depth(n: str) -> int:
        if n in layer:
            return layer[n]
        stack2 = [n]
        while stack2:
            cur = stack2[-1]
            missing = [p for p in dag_pred[cur] if p not in layer]
            if missing:
                stack2.extend(missing)
            else:
                layer[cur] = 1 + max((layer[p] for p in dag_pred[cur]), default=-1)
                stack2.pop()
        return layer[n]

    for i in ids:
        depth(i)

    n_layers = (max(layer.values()) + 1) if layer else 0
    rows: list[list[str]] = [[] for _ in range(n_layers)]
    for i in ids:
        rows[layer[i]].append(i)

    # Barycentre sweeps to reduce crossings.
    for sweep in range(4):
        order = range(1, n_layers) if sweep % 2 == 0 else range(n_layers - 2, -1, -1)
        for li in order:
            ref = li - 1 if sweep % 2 == 0 else li + 1
            idx = {n: k for k, n in enumerate(rows[ref])}
            nbrs = (lambda n: [p for p in dag_pred[n] if p in idx]) if sweep % 2 == 0 \
                else (lambda n: [s for s in succ[n] if s in idx and (n, s) not in back])
            orig = {n: k for k, n in enumerate(rows[li])}    # list.sort() empties the list mid-sort

            def bary(n: str, _nbrs=nbrs, _idx=idx, _orig=orig) -> float:
                ns = _nbrs(n)
                return sum(_idx[m] for m in ns) / len(ns) if ns else _orig[n]

            rows[li].sort(key=bary)

    lr = direction.upper() == "LR"
    pos: dict[str, tuple[float, float]] = {}
    margin = 60.0
    main = margin
    cross_totals = []
    for row in rows:
        tot = sum((sizes[n][1] if lr else sizes[n][0]) for n in row) + GAP_CROSS * max(len(row) - 1, 0)
        cross_totals.append(tot)
    widest = max(cross_totals, default=0)
    for row, tot in zip(rows, cross_totals):
        main_extent = max((sizes[n][0] if lr else sizes[n][1]) for n in row) if row else 0
        cross = margin + (widest - tot) / 2
        for n in row:
            w, h = sizes[n]
            if lr:
                pos[n] = (main, cross)
                cross += h + GAP_CROSS
            else:
                pos[n] = (cross, main)
                cross += w + GAP_CROSS
        main += main_extent + gap_main
    return pos


def grid_layout(ids: list[str], sizes: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    cols = max(1, math.ceil(math.sqrt(len(ids))))
    cw = max((sizes[i][0] for i in ids), default=BOX_W) + GAP_CROSS
    rh = max((sizes[i][1] for i in ids), default=BOX_H) + GAP_MAIN
    return {i: (60.0 + (k % cols) * cw, 60.0 + (k // cols) * rh) for k, i in enumerate(ids)}


def radial_layout(ids: list[str], sizes: dict[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    n = max(len(ids), 1)
    rx = max(260.0, n * 45.0)
    ry = max(180.0, n * 32.0)
    cx, cy = rx + 200.0, ry + 150.0
    out = {}
    for k, i in enumerate(ids):
        a = 2 * math.pi * k / n
        w, h = sizes[i]
        out[i] = (cx + math.cos(a) * rx - w / 2, cy + math.sin(a) * ry - h / 2)
    return out


def _layer_gap(arrows: list[dict[str, Any]], direction: str) -> float:
    """Distance between layers: wide enough that the widest arrow label fits on a short arrow."""
    if direction.upper() != "LR":
        return float(GAP_MAIN)
    widest = 0.0
    for a in arrows:
        label = _as_text(a.get("label", a.get("text")))
        if label:
            widest = max(widest, measure_text(wrap_label(label, 20), float(a.get("fontSize", 14)))[0])
    return float(min(max(GAP_MAIN, widest + 2 * BIND_GAP + 30), 280))


def _blocked(p0: tuple[float, float], p1: tuple[float, float],
             boxes: list[dict[str, Any]], pad: float) -> bool:
    """True if the segment p0→p1 passes through any box (inflated by *pad*)."""
    n = 48
    for k in range(1, n):
        x = p0[0] + (p1[0] - p0[0]) * k / n
        y = p0[1] + (p1[1] - p0[1]) * k / n
        for b in boxes:
            if (b["x"] - pad < x < b["x"] + b["width"] + pad
                    and b["y"] - pad < y < b["y"] + b["height"] + pad):
                return True
    return False


def _route_around(sp: tuple[float, float], ep: tuple[float, float],
                  obstacles: list[dict[str, Any]]) -> tuple[float, float] | None:
    """Pick a bend point so a curved arrow clears every obstacle; None if the straight line is clear."""
    if not _blocked(sp, ep, obstacles, 4):
        return None
    dx, dy = ep[0] - sp[0], ep[1] - sp[1]
    dist = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / dist, dx / dist
    mx, my = (sp[0] + ep[0]) / 2, (sp[1] + ep[1]) / 2
    for k in range(1, 12):
        for sign in (1, -1):
            off = sign * k * 45
            mid = (mx + nx * off, my + ny * off)
            # A smooth curve through `mid` bulges less than the polyline, so require generous clearance.
            if not _blocked(sp, mid, obstacles, 22) and not _blocked(mid, ep, obstacles, 22):
                return mid
    return None


# ── Skeleton → elements ─────────────────────────────────────────────────


def _as_text(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("text")
    if v is None:
        return None
    s = str(v)
    return s if s.strip() else None


def _endpoint(raw: Any) -> tuple[str, Any] | None:
    """('ref', handle) | ('pt', (x, y)) | None."""
    if isinstance(raw, str) and raw:
        return ("ref", raw)
    if isinstance(raw, dict):
        if isinstance(raw.get("id"), str) and raw["id"]:
            return ("ref", raw["id"])
        if isinstance(raw.get("x"), (int, float)) and isinstance(raw.get("y"), (int, float)):
            return ("pt", (float(raw["x"]), float(raw["y"])))
    return None


def build_elements(
    skeleton: list[dict[str, Any]],
    *,
    existing: list[dict[str, Any]] | None = None,
    direction: str = "TB",
    layout: str = "layered",
    origin: tuple[float, float] | None = None,
) -> BuildResult:
    """Turn a *skeleton* into complete Excalidraw elements.

    Skeleton items (all coordinates optional for shapes/text — they are laid out
    automatically)::

        {"id": "api", "type": "rectangle|ellipse|diamond", "label": "API", "x": 0, "y": 0,
         "width": 180, "height": 60, "backgroundColor": "#dbe9ff", ...}
        {"id": "note", "type": "text", "text": "Free text", "x": 0, "y": 0}
        {"type": "arrow", "start": "api", "end": "db", "label": "SQL"}

    ``layout`` is ``"layered"`` (default, follows the arrows), ``"grid"`` or
    ``"radial"`` and only affects shapes without explicit x/y.

    ``start``/``end`` reference skeleton ids (or ids already in *existing*), or
    are ``{"x":…, "y":…}`` free points.  ``from``/``to`` and ``text`` (on
    shapes/arrows) are accepted as aliases.  Raises :class:`SkeletonError` with
    *every* problem found, so the caller can fix them in one retry.

    *existing* elements are used as arrow targets and are mutated in place
    (their ``boundElements`` gain the new arrows).
    """
    existing = existing or []
    problems: list[str] = []
    warnings: list[str] = []

    used: set[str] = {e["id"] for e in existing if isinstance(e.get("id"), str)}
    ex_lookup: dict[str, dict[str, Any]] = {}
    for e in existing:
        if isinstance(e.get("id"), str):
            ex_lookup[e["id"]] = e
            h = (e.get("customData") or {}).get("handle")
            if isinstance(h, str):
                ex_lookup[h] = e

    # ── 1. validate ────────────────────────────────────────────────
    handles: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    for idx, raw in enumerate(skeleton):
        where = f"elements[{idx}]"
        if not isinstance(raw, dict):
            problems.append(f"{where}: must be an object, got {type(raw).__name__}")
            continue
        t = raw.get("type")
        if t not in SHAPE_TYPES + ARROW_TYPES + ("text",):
            problems.append(
                f"{where}: unsupported type {t!r}. Use rectangle, ellipse, diamond, text, arrow or line"
            )
            continue
        h = raw.get("id")
        if h is not None:
            if not isinstance(h, str) or not h:
                problems.append(f"{where}: 'id' must be a non-empty string")
                continue
            if h in handles or h in ex_lookup:
                problems.append(f"{where}: duplicate id {h!r}")
                continue
            handles[h] = idx
        items.append(raw)

    def resolvable(h: str) -> bool:
        return h in handles or h in ex_lookup

    known = sorted(set(handles) | {k for k in ex_lookup if k not in {e['id'] for e in existing}})
    for raw in items:
        if raw["type"] in ARROW_TYPES:
            for key, alias in (("start", "from"), ("end", "to")):
                ep = _endpoint(raw.get(key, raw.get(alias)))
                where = f"arrow {raw.get('id') or ''}".strip()
                if ep is None:
                    problems.append(f"{where}: missing '{key}' (a node id or {{x, y}})")
                elif ep[0] == "ref":
                    if not resolvable(ep[1]):
                        problems.append(
                            f"{where}: {key} {ep[1]!r} not found. Known ids: {', '.join(known) or '(none)'}"
                        )
                    elif ep[1] in handles and skeleton[handles[ep[1]]].get("type") in ARROW_TYPES:
                        problems.append(f"{where}: {key} {ep[1]!r} is an arrow; arrows connect shapes")
            s, e_ = _endpoint(raw.get("start", raw.get("from"))), _endpoint(raw.get("end", raw.get("to")))
            if s and e_ and s[0] == "ref" and e_[0] == "ref" and s[1] == e_[1]:
                problems.append(f"arrow {raw.get('id') or ''}: start and end are both {s[1]!r}; self-loops are not supported")
    if problems:
        raise SkeletonError(problems)

    # ── 2. shapes & text: sizes ────────────────────────────────────
    nodes = [it for it in items if it["type"] not in ARROW_TYPES]
    arrows = [it for it in items if it["type"] in ARROW_TYPES]

    node_info: dict[int, dict[str, Any]] = {}
    for it in nodes:
        t = it["type"]
        fs = float(it.get("fontSize", DEFAULT_FONT_SIZE))
        ff = int(it.get("fontFamily", DEFAULT_FONT_FAMILY))
        label = _as_text(it.get("label", it.get("text")))
        if t == "text":
            wrapped = str(label or "")
            tw, th = measure_text(wrapped, fs)
            w, h = float(it.get("width", tw)), float(it.get("height", th))
        else:
            factor_w, factor_h = {"diamond": (1.8, 1.8), "ellipse": (1.35, 1.35)}.get(t, (1.0, 1.0))
            if "width" in it:
                w = float(it["width"])
                wrap = max(6, int((w / factor_w - 2 * PAD) / (fs * CHAR_W)))
            else:
                wrap = WRAP_CHARS
                w = None  # type: ignore[assignment]
            wrapped = wrap_label(label, wrap) if label else ""
            tw, th = measure_text(wrapped, fs) if wrapped else (0, 0)
            if w is None:
                w = max(BOX_W, (tw + 2 * PAD) * factor_w)
            h = float(it["height"]) if "height" in it else max(BOX_H, (th + 2 * PAD) * factor_h)
        node_info[id(it)] = {"w": w, "h": h, "label": label, "fs": fs, "ff": ff}

    # ── 3. positions ───────────────────────────────────────────────
    def positioned(it: dict[str, Any]) -> bool:
        return isinstance(it.get("x"), (int, float)) and isinstance(it.get("y"), (int, float))

    to_place = [it for it in nodes if not positioned(it)]
    pos_by_obj: dict[int, tuple[float, float]] = {}
    if to_place:
        keyof = {id(it): f"n{k}" for k, it in enumerate(to_place)}
        by_handle = {it["id"]: keyof[id(it)] for it in to_place if "id" in it}
        sizes = {keyof[id(it)]: (node_info[id(it)]["w"], node_info[id(it)]["h"]) for it in to_place}
        edges: list[tuple[str, str]] = []
        for a in arrows:
            s, e_ = _endpoint(a.get("start", a.get("from"))), _endpoint(a.get("end", a.get("to")))
            if s and e_ and s[0] == "ref" and e_[0] == "ref" and s[1] in by_handle and e_[1] in by_handle:
                edges.append((by_handle[s[1]], by_handle[e_[1]]))
        ids = [keyof[id(it)] for it in to_place]
        if layout == "grid":
            laid = grid_layout(ids, sizes)
        elif layout == "radial":
            laid = radial_layout(ids, sizes)
        elif edges or len(ids) <= 6:
            laid = layered_layout(ids, edges, sizes, direction, gap_main=_layer_gap(arrows, direction))
        else:
            laid = grid_layout(ids, sizes)
        ox, oy = origin if origin else (0.0, 0.0)
        # layout margin is 60; shift so the block's top-left lands on origin (when given)
        if origin:
            mnx = min(p[0] for p in laid.values())
            mny = min(p[1] for p in laid.values())
            laid = {k: (v[0] - mnx + ox, v[1] - mny + oy) for k, v in laid.items()}
        for it in to_place:
            pos_by_obj[id(it)] = laid[keyof[id(it)]]

    # ── 4. build node elements ─────────────────────────────────────
    out: list[dict[str, Any]] = []
    ids_out: dict[str, str] = {}
    geom: dict[str, dict[str, Any]] = {}       # handle → element (new shapes)

    for it in nodes:
        info = node_info[id(it)]
        handle = it.get("id")
        x, y = (float(it["x"]), float(it["y"])) if positioned(it) else pos_by_obj[id(it)]
        if isinstance(handle, str) and _ID_RE.match(handle) and handle not in used:
            eid = handle
            used.add(eid)
        else:
            eid = make_id(handle if isinstance(handle, str) else f"node:{len(out)}:{x}:{y}", used)
        style = {k: it[k] for k in _STYLE_KEYS if k in it}
        if it["type"] == "text":
            wrapped = info["label"] or ""
            el = _text_element(
                eid, wrapped, wrapped, x, y, info["w"], info["h"],
                font_size=info["fs"], font_family=info["ff"], container_id=None,
                align=it.get("textAlign", "left"), valign="top",
                color=it.get("strokeColor", DEFAULT_STROKE),
            )
            for k, v in style.items():
                el[k] = v
            out.append(el)
        else:
            roundness = {"type": 3} if it["type"] == "rectangle" else None
            el = _common(eid, it["type"], x, y, info["w"], info["h"], roundness=roundness, **style)
            if isinstance(handle, str) and handle != eid:
                el["customData"] = {"handle": handle}
            elif isinstance(handle, str):
                el["customData"] = {"handle": handle}
            out.append(el)
            if info["label"]:
                out.append(_label_for_container(el, info["label"], used,
                                                font_size=info["fs"], font_family=info["ff"]))
        if isinstance(handle, str):
            ids_out[handle] = eid
            geom[handle] = el

    # ── 5. arrows ──────────────────────────────────────────────────
    def shape_of(handle: str) -> dict[str, Any]:
        return geom[handle] if handle in geom else ex_lookup[handle]

    pairs: set[tuple[str, str]] = set()
    resolved: list[tuple[dict[str, Any], Any, Any]] = []
    for a in arrows:
        s = _endpoint(a.get("start", a.get("from")))
        e_ = _endpoint(a.get("end", a.get("to")))
        assert s and e_
        resolved.append((a, s, e_))
        if s[0] == "ref" and e_[0] == "ref":
            pairs.add((shape_of(s[1])["id"], shape_of(e_[1])["id"]))

    for a, s, e_ in resolved:
        s_shape = shape_of(s[1]) if s[0] == "ref" else None
        e_shape = shape_of(e_[1]) if e_[0] == "ref" else None
        if (s_shape and s_shape.get("type") == "text") or (e_shape and e_shape.get("type") == "text"):
            warnings.append("arrow connects to a free text element; it was drawn but not bound")
        sc = ((s_shape["x"] + s_shape["width"] / 2, s_shape["y"] + s_shape["height"] / 2)
              if s_shape else s[1])
        ec = ((e_shape["x"] + e_shape["width"] / 2, e_shape["y"] + e_shape["height"] / 2)
              if e_shape else e_[1])
        # Offset anti-parallel pairs so A→B and B→A do not overlap.
        off = 0.0
        if s_shape and e_shape and (e_shape["id"], s_shape["id"]) in pairs:
            off = 12.0          # same sign for both: each shifts to its own right-hand side
        dx, dy = ec[0] - sc[0], ec[1] - sc[1]
        dist = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / dist * off, dx / dist * off
        sp = _edge_point(s_shape, ec[0] + nx, ec[1] + ny, BIND_GAP) if s_shape else s[1]
        ep = _edge_point(e_shape, sc[0] + nx, sc[1] + ny, BIND_GAP) if e_shape else e_[1]
        sp = (sp[0] + nx, sp[1] + ny) if s_shape else sp
        ep = (ep[0] + nx, ep[1] + ny) if e_shape else ep
        bend: tuple[float, float] | None = None
        if a["type"] == "arrow" and s_shape and e_shape and off == 0 \
                and s_shape.get("type") in SHAPE_TYPES and e_shape.get("type") in SHAPE_TYPES:
            blockers = [b for b in list(geom.values()) + existing
                        if isinstance(b, dict) and b.get("type") in SHAPE_TYPES
                        and b["id"] not in (s_shape["id"], e_shape["id"])]
            bend = _route_around(sp, ep, blockers)
            if bend:
                sp = _edge_point(s_shape, bend[0], bend[1], BIND_GAP)
                ep = _edge_point(e_shape, bend[0], bend[1], BIND_GAP)

        handle = a.get("id")
        aid = make_id(handle if isinstance(handle, str)
                      else f"arrow:{(s_shape or {}).get('id', s[1])}>{(e_shape or {}).get('id', e_[1])}", used)
        style = {k: a[k] for k in _STYLE_KEYS if k in a}
        is_arrow = a["type"] == "arrow"
        pts = [[0, 0], [_r(ep[0] - sp[0]), _r(ep[1] - sp[1])]]
        if bend:
            pts = [[0, 0], [_r(bend[0] - sp[0]), _r(bend[1] - sp[1])], pts[1]]
        arrow = _common(
            aid, a["type"], sp[0], sp[1],
            max(p[0] for p in pts) - min(p[0] for p in pts),
            max(p[1] for p in pts) - min(p[1] for p in pts),
            roughness=0, **({"roundness": {"type": 2}} if bend else {}), **style,
        )
        arrow.update(
            points=pts,
            lastCommittedPoint=None, elbowed=False,
            startBinding=None, endBinding=None,
            startArrowhead=a.get("startArrowhead"),
            endArrowhead=a.get("endArrowhead", "arrow" if is_arrow else None),
        )
        if is_arrow:
            if s_shape and s_shape.get("type") != "text":
                arrow["startBinding"] = {"elementId": s_shape["id"], "focus": 0, "gap": BIND_GAP}
                s_shape.setdefault("boundElements", []) 
                if s_shape["boundElements"] is None:
                    s_shape["boundElements"] = []
                s_shape["boundElements"].append({"id": aid, "type": "arrow"})
            if e_shape and e_shape.get("type") != "text":
                arrow["endBinding"] = {"elementId": e_shape["id"], "focus": 0, "gap": BIND_GAP}
                e_shape.setdefault("boundElements", [])
                if e_shape["boundElements"] is None:
                    e_shape["boundElements"] = []
                e_shape["boundElements"].append({"id": aid, "type": "arrow"})
        out.append(arrow)
        label = _as_text(a.get("label", a.get("text")))
        if label:
            fs = float(a.get("fontSize", 14))
            wrapped = wrap_label(label, 20)
            tw, th = measure_text(wrapped, fs)
            mx, my = ((bend[0], bend[1]) if bend else ((sp[0] + ep[0]) / 2, (sp[1] + ep[1]) / 2))
            tid = make_id(aid + ":label", used)
            txt = _text_element(
                tid, wrapped, label, mx - tw / 2, my - th / 2, tw, th, font_size=fs,
                font_family=int(a.get("fontFamily", DEFAULT_FONT_FAMILY)),
                container_id=aid, align="center", valign="middle",
                color=arrow.get("strokeColor", DEFAULT_STROKE),
            )
            arrow["boundElements"].append({"type": "text", "id": tid})
            out.append(txt)
        if isinstance(handle, str):
            ids_out[handle] = aid

    return BuildResult(out, ids_out, warnings)


def set_label(elements: list[dict[str, Any]], shape: dict[str, Any], text: str) -> None:
    """Set (or create) the bound label of *shape*; grows the shape if the text needs room."""
    used = {e["id"] for e in elements if isinstance(e.get("id"), str)}
    by_id = {e["id"]: e for e in elements if isinstance(e.get("id"), str)}
    existing = next((by_id[r["id"]] for r in (shape.get("boundElements") or [])
                     if isinstance(r, dict) and r.get("type") == "text" and r.get("id") in by_id), None)
    fs = float(existing["fontSize"]) if existing else DEFAULT_FONT_SIZE
    ff = int(existing["fontFamily"]) if existing else DEFAULT_FONT_FAMILY
    if shape["type"] in ARROW_TYPES:
        fs = float(existing["fontSize"]) if existing else 14
        wrapped = wrap_label(text, 20)
        tw, th = measure_text(wrapped, fs)
        pts = shape["points"]
        cx, cy = shape["x"] + pts[-1][0] / 2, shape["y"] + pts[-1][1] / 2
    else:
        factor = {"diamond": 1.8, "ellipse": 1.35}.get(shape["type"], 1.0)
        wrap = max(6, int((shape["width"] / factor - 2 * PAD) / (fs * CHAR_W)))
        wrapped = wrap_label(text, wrap)
        tw, th = measure_text(wrapped, fs)
        need_w, need_h = (tw + 2 * PAD) * factor, (th + 2 * PAD) * factor
        if need_w > shape["width"]:
            shape["x"] = _r(shape["x"] - (need_w - shape["width"]) / 2)
            shape["width"] = _r(need_w)
        if need_h > shape["height"]:
            shape["y"] = _r(shape["y"] - (need_h - shape["height"]) / 2)
            shape["height"] = _r(need_h)
        cx, cy = shape["x"] + shape["width"] / 2, shape["y"] + shape["height"] / 2
    if existing is None:
        tid = make_id(shape["id"] + ":label", used)
        existing = _text_element(tid, wrapped, text, cx - tw / 2, cy - th / 2, tw, th,
                                 font_size=fs, font_family=ff, container_id=shape["id"],
                                 align="center", valign="middle",
                                 color=shape.get("strokeColor", DEFAULT_STROKE))
        if shape.get("boundElements") is None:
            shape["boundElements"] = []
        shape["boundElements"].append({"type": "text", "id": tid})
        elements.append(existing)
    else:
        existing.update(text=wrapped, originalText=text, width=tw, height=th,
                        x=_r(cx - tw / 2), y=_r(cy - th / 2))
        existing["version"] = existing.get("version", 1) + 1


# ── Scene payload ───────────────────────────────────────────────────────


def scene_payload(elements: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "excalidraw", "version": EX_VERSION, "source": EX_SOURCE,
        "elements": elements, "appState": dict(APP_STATE), "files": {},
    }


def bounds(elements: list[dict[str, Any]]) -> tuple[float, float, float, float] | None:
    live = [e for e in elements if isinstance(e, dict) and not e.get("isDeleted")
            and isinstance(e.get("x"), (int, float)) and isinstance(e.get("y"), (int, float))]
    if not live:
        return None
    x0 = min(e["x"] for e in live)
    y0 = min(e["y"] for e in live)
    x1 = max(e["x"] + abs(e.get("width") or 0) for e in live)
    y1 = max(e["y"] + abs(e.get("height") or 0) for e in live)
    return x0, y0, x1, y1


# ── Validation ──────────────────────────────────────────────────────────

_DEFAULT_FIELDS = ("seed", "version", "versionNonce", "isDeleted", "groupIds",
                   "frameId", "roundness", "updated", "link", "locked", "angle",
                   "strokeColor", "backgroundColor", "fillStyle", "strokeWidth",
                   "strokeStyle", "roughness", "opacity")


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_scene(payload: Any) -> list[Issue]:
    """Report every problem in *payload*.  Pure; never mutates."""
    out: list[Issue] = []

    def add(sev: str, code: str, msg: str, eid: str | None = None, fixable: bool = False) -> None:
        out.append(Issue(sev, code, msg, eid, fixable))

    if not isinstance(payload, dict):
        add("error", "not_object", "Scene root must be a JSON object")
        return out
    if payload.get("type") != "excalidraw":
        add("warning", "bad_type", 'Root "type" should be "excalidraw"', fixable=True)
    els = payload.get("elements")
    if not isinstance(els, list):
        add("error", "no_elements", 'Scene needs an "elements" array')
        return out

    by_id: dict[str, dict[str, Any]] = {}
    for i, e in enumerate(els):
        if not isinstance(e, dict):
            add("error", "not_object", f"elements[{i}] is not an object")
            continue
        eid = e.get("id")
        if not isinstance(eid, str) or not eid:
            add("error", "missing_id", f"elements[{i}] has no id", fixable=True)
            continue
        if eid in by_id:
            add("error", "duplicate_id", f"Duplicate element id {eid!r}", eid, True)
            continue
        by_id[eid] = e

    for eid, e in by_id.items():
        t = e.get("type")
        if t not in KNOWN_TYPES:
            add("warning", "unknown_type", f"Unknown element type {t!r} (left untouched)", eid)
            continue
        for k in ("x", "y"):
            if not _is_num(e.get(k)):
                add("error", "bad_geometry", f"{k} must be a number", eid)
        for k in ("width", "height"):
            if not _is_num(e.get(k)):
                add("error", "bad_geometry", f"{k} must be a number", eid, True)
        missing = [k for k in _DEFAULT_FIELDS if k not in e]
        if missing:
            add("warning", "missing_defaults", f"Missing fields: {', '.join(missing)}", eid, True)

        if t != "text" and any(isinstance(e.get(k), str) and e.get(k).strip() for k in ("text", "label")):
            add("error", "inline_label",
                f"{t} has inline text/label — Excalidraw ignores it. Labels must be bound text elements",
                eid, True)

        if t in ARROW_TYPES:
            pts = e.get("points")
            ok = isinstance(pts, list) and len(pts) >= 2 and all(
                isinstance(p, list) and len(p) == 2 and all(_is_num(c) for c in p) for p in pts)
            if not ok:
                add("error", "bad_points", "points must be a list of ≥2 [x, y] pairs relative to the arrow", eid, True)
            elif pts[0] != [0, 0] and pts[0] != [0.0, 0.0]:
                add("warning", "points_origin", "first point should be [0, 0] (points are relative to x,y)", eid, True)
            for side in ("startBinding", "endBinding"):
                b = e.get(side)
                if isinstance(b, dict):
                    target = by_id.get(b.get("elementId"))
                    if target is None:
                        add("error", "dangling_binding", f"{side} points at missing element {b.get('elementId')!r}", eid, True)
                    elif not any(isinstance(r, dict) and r.get("id") == eid for r in (target.get("boundElements") or [])):
                        add("error", "one_way_binding",
                            f"{side} → {target['id']!r} but that shape does not list this arrow in boundElements "
                            "(arrow would detach on drag)", eid, True)

        if t == "text":
            cid = e.get("containerId")
            if cid:
                cont = by_id.get(cid)
                if cont is None:
                    add("error", "orphan_text", f"containerId {cid!r} not found", eid, True)
                elif not any(isinstance(r, dict) and r.get("id") == eid for r in (cont.get("boundElements") or [])):
                    add("error", "unbound_text", f"container {cid!r} does not list this text in boundElements", eid, True)
            if not _ID_RE.match(eid):
                add("warning", "text_id_length",
                    f"text id {eid!r} is not 8 alphanumeric chars (Obsidian Text Elements block ref)", eid, True)
            if not isinstance(e.get("text"), str):
                add("error", "bad_text", "text element needs a string 'text'", eid)

        for r in (e.get("boundElements") or []):
            if isinstance(r, dict) and r.get("id") not in by_id:
                add("warning", "dangling_bound_ref", f"boundElements references missing {r.get('id')!r}", eid, True)

    return out


# ── Repair ──────────────────────────────────────────────────────────────


def repair_scene(payload: Any) -> tuple[dict[str, Any], list[str]]:
    """Fix everything fixable.  Returns (new payload, human-readable change log).

    Never drops user content it does not understand (unknown element types,
    images, frames are kept as-is).  Raises :class:`ValueError` when the root is
    not a scene at all.
    """
    if not isinstance(payload, dict):
        raise ValueError("Scene root must be a JSON object")
    pl = json.loads(json.dumps(payload))      # deep copy
    changes: list[str] = []

    if pl.get("type") != "excalidraw":
        pl["type"] = "excalidraw"
        changes.append('set root type to "excalidraw"')
    pl.setdefault("version", EX_VERSION)
    pl.setdefault("source", EX_SOURCE)
    if not isinstance(pl.get("appState"), dict):
        pl["appState"] = dict(APP_STATE)
    if not isinstance(pl.get("files"), dict):
        pl["files"] = {}
    els_in = pl.get("elements")
    if not isinstance(els_in, list):
        raise ValueError('Scene needs an "elements" array')

    used: set[str] = set()
    els: list[dict[str, Any]] = []
    for i, e in enumerate(els_in):
        if not isinstance(e, dict) or not isinstance(e.get("type"), str):
            changes.append(f"dropped elements[{i}] (not an element object)")
            continue
        eid = e.get("id")
        if not isinstance(eid, str) or not eid or eid in used:
            new = make_id(f"{e.get('type')}:{i}:{e.get('x')}:{e.get('y')}", used)
            changes.append(f"assigned id {new} to elements[{i}] ({'duplicate' if eid else 'missing'} id)")
            e["id"] = new
        else:
            used.add(eid)
        els.append(e)

    by_id = {e["id"]: e for e in els}
    extra: list[dict[str, Any]] = []

    for e in els:
        t = e["type"]
        if t not in KNOWN_TYPES:
            continue
        # defaults
        base = _common(e["id"], t, e.get("x", 0), e.get("y", 0), e.get("width", 0), e.get("height", 0))
        filled = [k for k in _DEFAULT_FIELDS if k not in e]
        for k in filled:
            e[k] = base[k]
        if t not in ("text",) and "boundElements" not in e:
            e["boundElements"] = []
        if filled:
            changes.append(f"{t} {e['id']}: filled {len(filled)} missing field(s)")
        if not _is_num(e.get("x")):
            e["x"] = 0
        if not _is_num(e.get("y")):
            e["y"] = 0

        if t == "text":
            txt = e.get("text") if isinstance(e.get("text"), str) else str(e.get("text") or "")
            e["text"] = txt
            e.setdefault("originalText", txt)
            e.setdefault("fontSize", DEFAULT_FONT_SIZE)
            e.setdefault("fontFamily", DEFAULT_FONT_FAMILY)
            e.setdefault("textAlign", "left" if not e.get("containerId") else "center")
            e.setdefault("verticalAlign", "top" if not e.get("containerId") else "middle")
            e.setdefault("containerId", None)
            e.setdefault("autoResize", True)
            e.setdefault("lineHeight", LINE_H)
            if not _is_num(e.get("width")) or not _is_num(e.get("height")) or not e.get("width"):
                e["width"], e["height"] = measure_text(txt, e["fontSize"])
                changes.append(f"text {e['id']}: measured size")
            if e.get("boundElements") == []:
                e["boundElements"] = None
        else:
            for k, dflt in (("width", BOX_W if t in SHAPE_TYPES else 0), ("height", BOX_H if t in SHAPE_TYPES else 0)):
                if not _is_num(e.get(k)):
                    e[k] = dflt
                    changes.append(f"{t} {e['id']}: defaulted {k}")

        if t in ARROW_TYPES:
            pts = e.get("points")
            ok = isinstance(pts, list) and len(pts) >= 2 and all(
                isinstance(p, list) and len(p) == 2 and all(_is_num(c) for c in p) for p in pts)
            if not ok:
                e["points"] = [[0, 0], [_r(e.get("width", 0)), _r(e.get("height", 0))]]
                changes.append(f"{t} {e['id']}: rebuilt points from width/height")
            elif pts[0] not in ([0, 0], [0.0, 0.0]):
                ox, oy = pts[0]
                if abs(ox - e["x"]) < 1 and abs(oy - e["y"]) < 1:
                    # Absolute coordinates duplicated in x,y (common LLM mistake): keep x,y.
                    note = "points were absolute; made them relative"
                else:
                    # Excalidraw's own normalisation: shift origin to the first point.
                    e["x"], e["y"] = _r(e["x"] + ox), _r(e["y"] + oy)
                    note = "re-based points to start at [0, 0]"
                e["points"] = [[_r(p[0] - ox), _r(p[1] - oy)] for p in pts]
                changes.append(f"{t} {e['id']}: {note}")
            # Size must match the point extents (Excalidraw uses it for hit-testing/bounds).
            xs = [p[0] for p in e["points"]]
            ys = [p[1] for p in e["points"]]
            e["width"], e["height"] = _r(max(xs) - min(xs)), _r(max(ys) - min(ys))
            e.setdefault("startBinding", None)
            e.setdefault("endBinding", None)
            e.setdefault("startArrowhead", None)
            e.setdefault("endArrowhead", "arrow" if t == "arrow" else None)
            e.setdefault("lastCommittedPoint", None)
            e.setdefault("elbowed", False)

    # inline labels → bound text
    for e in list(els):
        t = e["type"]
        if t == "text" or t not in SHAPE_TYPES + ARROW_TYPES:
            continue
        inline = None
        for k in ("text", "label"):
            v = _as_text(e.get(k))
            if v:
                inline = v if inline is None else inline
            e.pop(k, None)
        if inline and not any(isinstance(r, dict) and r.get("type") == "text" for r in (e.get("boundElements") or [])):
            if t in SHAPE_TYPES:
                lab = _label_for_container(e, inline, used)
            else:
                pts = e["points"]
                mx = e["x"] + pts[-1][0] / 2
                my = e["y"] + pts[-1][1] / 2
                wrapped = wrap_label(inline, 20)
                tw, th = measure_text(wrapped, 14)
                tid = make_id(e["id"] + ":label", used)
                lab = _text_element(tid, wrapped, inline, mx - tw / 2, my - th / 2, tw, th,
                                    font_size=14, font_family=DEFAULT_FONT_FAMILY,
                                    container_id=e["id"], align="center", valign="middle",
                                    color=e.get("strokeColor", DEFAULT_STROKE))
                e.setdefault("boundElements", [])
                e["boundElements"].append({"type": "text", "id": tid})
            extra.append(lab)
            by_id[lab["id"]] = lab
            changes.append(f"{t} {e['id']}: converted inline label {inline!r} into a bound text element")
    els.extend(extra)

    # text ids → 8 chars (update container refs)
    for e in els:
        if e["type"] == "text" and not _ID_RE.match(e["id"]):
            old = e["id"]
            new = make_id(old, used)
            e["id"] = new
            by_id.pop(old, None)
            by_id[new] = e
            for c in els:
                for r in (c.get("boundElements") or []):
                    if isinstance(r, dict) and r.get("id") == old:
                        r["id"] = new
            changes.append(f"text {old}: re-keyed to 8-char id {new}")

    # reciprocal references
    for e in els:
        t = e["type"]
        if t in ARROW_TYPES:
            for side in ("startBinding", "endBinding"):
                b = e.get(side)
                if not isinstance(b, dict):
                    e[side] = None
                    continue
                tgt = by_id.get(b.get("elementId"))
                if tgt is None:
                    e[side] = None
                    changes.append(f"{t} {e['id']}: removed {side} to missing element")
                    continue
                b.setdefault("focus", 0)
                b.setdefault("gap", BIND_GAP)
                be = tgt.get("boundElements")
                if be is None:
                    be = tgt["boundElements"] = []
                if not any(isinstance(r, dict) and r.get("id") == e["id"] for r in be):
                    be.append({"id": e["id"], "type": "arrow"})
                    changes.append(f"{tgt['type']} {tgt['id']}: now lists arrow {e['id']} (two-way binding)")
        if t == "text" and e.get("containerId"):
            cont = by_id.get(e["containerId"])
            if cont is None:
                e["containerId"] = None
                changes.append(f"text {e['id']}: containerId pointed nowhere; made free-standing")
            else:
                be = cont.get("boundElements")
                if be is None:
                    be = cont["boundElements"] = []
                if not any(isinstance(r, dict) and r.get("id") == e["id"] for r in be):
                    be.append({"type": "text", "id": e["id"]})
                    changes.append(f"{cont['type']} {cont['id']}: now lists its label text {e['id']}")
    for e in els:
        be = e.get("boundElements")
        if isinstance(be, list):
            keep = [r for r in be if isinstance(r, dict) and r.get("id") in by_id]
            if len(keep) != len(be):
                e["boundElements"] = keep
                changes.append(f"{e['type']} {e['id']}: dropped {len(be) - len(keep)} dangling boundElements ref(s)")

    pl["elements"] = els
    return pl, changes


def summarize_scene(payload: dict[str, Any]) -> dict[str, Any]:
    """Compact, LLM-friendly view: nodes, connections, free text."""
    els = [e for e in payload.get("elements", []) if isinstance(e, dict) and not e.get("isDeleted")]
    by_id = {e.get("id"): e for e in els}

    def label_of(e: dict[str, Any]) -> str:
        for r in (e.get("boundElements") or []):
            if isinstance(r, dict) and r.get("type") == "text":
                t = by_id.get(r.get("id"))
                if t:
                    return t.get("originalText") or t.get("text") or ""
        return ""

    def name(i: Any) -> str:
        t = by_id.get(i)
        if not t:
            return str(i)
        return (t.get("customData") or {}).get("handle") or t["id"]

    nodes, conns, texts = [], [], []
    for e in els:
        t = e.get("type")
        if t in SHAPE_TYPES:
            nodes.append({"id": e["id"], "handle": (e.get("customData") or {}).get("handle"),
                          "type": t, "label": label_of(e),
                          "x": e.get("x"), "y": e.get("y"), "w": e.get("width"), "h": e.get("height")})
        elif t in ARROW_TYPES:
            sb, eb = e.get("startBinding") or {}, e.get("endBinding") or {}
            conns.append({"id": e["id"], "type": t, "label": label_of(e),
                          "from": name(sb.get("elementId")) if sb else None,
                          "to": name(eb.get("elementId")) if eb else None})
        elif t == "text" and not e.get("containerId"):
            texts.append({"id": e["id"], "text": e.get("originalText") or e.get("text"),
                          "x": e.get("x"), "y": e.get("y")})
    return {"nodes": nodes, "connections": conns, "free_text": texts}


# ── LZ-String (Obsidian stores compressed-json as LZString base64) ──────

_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="
_B64_REV = {c: i for i, c in enumerate(_B64)}


def _join_utf16(parts: list[str]) -> str:
    """JS strings are UTF-16 code units; recombine surrogate pairs into code points."""
    s = "".join(parts)
    try:
        return s.encode("utf-16", "surrogatepass").decode("utf-16")
    except UnicodeDecodeError:
        return s


def lz_decompress_base64(data: str) -> str | None:
    """Port of LZString.decompressFromBase64.  Returns None on malformed input."""
    s = re.sub(r"\s+", "", data)
    if not s:
        return None
    length = len(s)

    def get(index: int) -> int:
        return _B64_REV.get(s[index], 0) if index < length else 0

    val, position, index = get(0), 32, 1

    def read(nbits: int) -> int:
        nonlocal val, position, index
        bits, power = 0, 1
        for _ in range(nbits):
            resb = val & position
            position >>= 1
            if position == 0:
                position = 32
                val = get(index)
                index += 1
            bits |= (1 if resb > 0 else 0) * power
            power <<= 1
        return bits

    dictionary: dict[int, str] = {}
    enlarge_in, dict_size, num_bits = 4, 4, 3
    nxt = read(2)
    if nxt == 0:
        c = chr(read(8))
    elif nxt == 1:
        c = chr(read(16))
    else:
        return ""
    dictionary[3] = c
    w = c
    result = [c]
    while True:
        if index > length:
            return None
        cc = read(num_bits)
        if cc == 0:
            dictionary[dict_size] = chr(read(8))
            dict_size += 1
            cc = dict_size - 1
            enlarge_in -= 1
        elif cc == 1:
            dictionary[dict_size] = chr(read(16))
            dict_size += 1
            cc = dict_size - 1
            enlarge_in -= 1
        elif cc == 2:
            return _join_utf16(result)
        if enlarge_in == 0:
            enlarge_in = 2 ** num_bits
            num_bits += 1
        if cc in dictionary:
            entry = dictionary[cc]
        elif cc == dict_size:
            entry = w + w[0]
        else:
            return None
        result.append(entry)
        dictionary[dict_size] = w + entry[0]
        dict_size += 1
        enlarge_in -= 1
        w = entry
        if enlarge_in == 0:
            enlarge_in = 2 ** num_bits
            num_bits += 1


# ── File I/O ────────────────────────────────────────────────────────────

_DRAWING_RE = re.compile(r"##[ \t]+Drawing[ \t]*\r?\n```(compressed-json|json)[ \t]*\r?\n(.*?)\r?\n?```", re.DOTALL)
_TEXT_SECTION_RE = re.compile(r"^## Text Elements[ \t]*\r?\n(.*?)(?=^## |^%%)", re.DOTALL | re.MULTILINE)

_PLUGIN_BANNER = (
    "==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this document. ⚠== "
    "You can decompress Drawing data with the command palette: 'Decompress current Excalidraw file'. "
    "For more info check in plugin settings under 'Saving'"
)


def parse_drawing(content: str) -> ParsedDrawing:
    """Extract the scene from an ``.excalidraw.md`` body (plain or compressed)."""
    stripped = content.strip()
    if stripped.startswith("{"):                       # bare scene JSON
        try:
            return ParsedDrawing(json.loads(stripped))
        except json.JSONDecodeError as exc:
            return ParsedDrawing(None, error=f"Content looks like JSON but does not parse: {exc}")
    m = _DRAWING_RE.search(content)
    if not m:
        m2 = re.search(r"```json\s*\n(.*?)\n```", content, re.DOTALL)   # legacy bare block
        if not m2:
            return ParsedDrawing(None, error='No "## Drawing" block with a ```json (or compressed-json) fence found.')
        kind, body = "json", m2.group(1)
    else:
        kind, body = m.group(1), m.group(2)
    if kind == "compressed-json":
        raw = lz_decompress_base64(body)
        if raw is None:
            return ParsedDrawing(None, True, "compressed-json block could not be decompressed")
        body = raw
    try:
        return ParsedDrawing(json.loads(body), kind == "compressed-json")
    except json.JSONDecodeError as exc:
        return ParsedDrawing(None, kind == "compressed-json", f"Drawing JSON is invalid: {exc}")


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _text_section(elements: list[dict[str, Any]]) -> str:
    parts = []
    for e in elements:
        if e.get("type") == "text" and not e.get("isDeleted") and _ID_RE.match(str(e.get("id", ""))):
            parts.append(f"{e.get('originalText') or e.get('text') or ''} ^{e['id']}\n\n")
    return "".join(parts)


def build_drawing_file(title: str, payload: dict[str, Any]) -> str:
    """Canonical ``.excalidraw.md`` the Obsidian plugin writes itself."""
    safe_title = " ".join(str(title).split())
    return (
        "---\n"
        "excalidraw-plugin: parsed\n"
        "tags: [excalidraw, diagram]\n"
        f"title: {json.dumps(safe_title, ensure_ascii=False)}\n"
        "---\n"
        f"{_PLUGIN_BANNER}\n\n\n"
        f"# {safe_title}\n\n"
        "# Excalidraw Data\n\n"
        "## Text Elements\n"
        f"{_text_section(payload.get('elements', []))}"
        "%%\n"
        "## Drawing\n"
        "```json\n"
        f"{_json(payload)}\n"
        "```\n"
        "%%\n"
    )


def ensure_plugin_frontmatter(content: str) -> str:
    if content.startswith("---"):
        end = content.find("\n---", 3)
        if end != -1:
            fm = content[3:end]
            if re.search(r"^excalidraw-plugin\s*:", fm, re.MULTILINE):
                return content
            return content[:3] + "\nexcalidraw-plugin: parsed" + content[3:]
    return "---\nexcalidraw-plugin: parsed\ntags: [excalidraw]\n---\n" + content


def rewrite_drawing_file(original: str, payload: dict[str, Any]) -> str:
    """Replace only the Text Elements + Drawing sections of *original*.

    Everything else — frontmatter, markdown above the data heading, and the
    ``## Embedded Files`` section (images!) — is preserved byte-for-byte.
    Output is uncompressed JSON (the plugin reads both and will re-compress on
    its next save if the user has compression enabled).
    """
    m = _DRAWING_RE.search(original)
    if not m:
        m2 = re.search(r"```json\s*\n.*?\n```", original, re.DOTALL)
        if not m2:
            raise ValueError("No drawing block to rewrite")
        before, after = original[:m2.start()], original[m2.end():]
        block = f"## Drawing\n```json\n{_json(payload)}\n```"
    else:
        before, after = original[:m.start()], original[m.end():]
        block = f"## Drawing\n```json\n{_json(payload)}\n```"
    if not re.search(r"%%[ \t]*\r?\n?\s*$", before):
        before = before.rstrip("\n") + "\n%%\n"
    if not re.match(r"\s*%%", after):
        block += "\n%%"
    text = before + block + after

    section = _text_section(payload.get("elements", []))
    if _TEXT_SECTION_RE.search(text):
        text = _TEXT_SECTION_RE.sub(lambda _m: "## Text Elements\n" + section, text, count=1)
    else:
        marker = re.search(r"^%%[ \t]*\r?\n##[ \t]+Drawing", text, re.MULTILINE)
        head = "" if re.search(r"^# Excalidraw Data", text, re.MULTILINE) else "# Excalidraw Data\n\n"
        ins = f"{head}## Text Elements\n{section}"
        text = text[:marker.start()] + ins + text[marker.start():] if marker else text
    return text
