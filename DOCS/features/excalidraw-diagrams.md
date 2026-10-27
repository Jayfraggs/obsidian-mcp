# Feature: Excalidraw Diagrams

## Summary

The server creates, edits, validates and repairs Excalidraw drawings
(`*.excalidraw.md`) that Obsidian's Excalidraw plugin opens natively. **The AI never
writes drawing JSON.** It describes a diagram as a short list of nodes and arrows (a
*skeleton*); the server turns that into a complete, valid scene.

## Why

LLMs asked to write Excalidraw JSON produce scenes that look right but break in ways
Excalidraw silently tolerates or "fixes" by dropping data:

| Mistake | What Excalidraw does |
|---------|----------------------|
| `text` placed on a rectangle/arrow | Ignores it — the label never appears. Labels must be separate `text` elements bound to the shape (`containerId` + the shape's `boundElements`). |
| Arrow knows its shape but the shape does not list the arrow | Arrow detaches when the shape is dragged. |
| Missing `seed`, `version`, `groupIds`, `isDeleted`, … | Re-saved with defaults; unpredictable. |
| Absolute arrow `points` | Arrow drawn in the wrong place (points are relative to the arrow's `x, y`). |
| Text ids that are not 8 characters | Not matched to the plugin's `## Text Elements` block references. |

The previous generators had the first problem themselves (labels were inline `text`),
so even `generate_architecture` output lost its labels.

## Architecture

```
LLM ──skeleton──▶ ExcalidrawService ──▶ excalidraw_scene (engine) ──▶ .excalidraw.md
                        ▲                      │
 create_note/update_note│                      ├─ build_elements   skeleton → full elements
        on *.excalidraw.md ─▶ write_raw        ├─ validate_scene / repair_scene
                                               ├─ layered / grid / radial layout + arrow routing
                                               └─ parse_drawing (plain + compressed-json), rewrite_drawing_file
```

- `plugins/excalidraw_scene.py` — pure data in / data out (no vault access). Everything
  that knows how a valid scene looks lives here.
- `plugins/excalidraw.py` — `ExcalidrawService`, the vault-facing layer (reads/writes notes).
- `tools/plugins.py` — MCP tool registration; `tools/core.py` — the write guard.

## Tools

Excalidraw tools registered: `excalidraw_get_schema`, `excalidraw_create_diagram`, `excalidraw_generate_flowchart`, `excalidraw_generate_architecture`, `excalidraw_generate_concept_map`, `excalidraw_edit_diagram`, `excalidraw_validate`, `excalidraw_parse_elements`, `excalidraw_add_annotation`, `excalidraw_write_script`, `excalidraw_embed_in_note`, `excalidraw_install_scripts`, `excalidraw_list_bundled_scripts`.

| Tool | Purpose |
|------|---------|
| `excalidraw_get_schema` | Skeleton format, an example and the rules. The AI calls this once first. |
| `excalidraw_create_diagram` | **Any** diagram from nodes + arrows; coordinates optional. |
| `excalidraw_generate_flowchart` | Flowchart from steps with `next` links; start/decision/process shapes chosen for you. |
| `excalidraw_generate_architecture` | Typed nodes (`service`, `database`, `queue`, `external`, `user`, `container`) + edges. |
| `excalidraw_generate_concept_map` | Radial map: centre → branches → leaves. |
| `excalidraw_edit_diagram` | Add / remove / relabel / restyle elements in an existing drawing. |
| `excalidraw_validate` | List problems in any drawing; `repair=true` fixes them in place. |
| `excalidraw_parse_elements` | Read a drawing (plain or compressed). `compact=true` returns nodes/connections only. |
| `excalidraw_add_annotation` | Add a floating text element. |
| `excalidraw_install_scripts`, `excalidraw_list_bundled_scripts`, `excalidraw_write_script`, `excalidraw_embed_in_note` | Unchanged: Script Engine files and `![[…]]` embeds. |

All creation tools refuse to overwrite unless `overwrite=true`, and **write nothing** when the
input is invalid.

### Skeleton format

`excalidraw_create_diagram(path, title, elements, direction="TB", layout="layered", overwrite=False)`

| Element | Fields |
|---------|--------|
| `rectangle` · `ellipse` · `diamond` | `id` (your handle), `label` (alias `text`), optional `x, y, width, height`, style |
| `text` | `text`, optional `x, y`, `fontSize`, `fontFamily`, `textAlign` |
| `arrow` · `line` | `start`, `end` (aliases `from`, `to`) = a node id, `{"id": …}` or a free point `{"x":…, "y":…}`; optional `label`, `startArrowhead`, `endArrowhead` |

Style keys (any element): `strokeColor`, `backgroundColor`, `fillStyle`, `strokeWidth`,
`strokeStyle` (`solid`/`dashed`/`dotted`), `roughness`, `opacity`, `fontSize`, `fontFamily`.
Palette used by the generators: blue `#dbe9ff`, yellow `#fff3bf`, green `#e8f5e9`,
purple `#fce8ff`, orange `#ffeedd`, grey `#f0f0f0`.

```json
{
  "path": "Diagrams/Checkout",
  "title": "Checkout flow",
  "direction": "LR",
  "elements": [
    {
      "id": "user",
      "type": "ellipse",
      "label": "User",
      "backgroundColor": "#ffeedd"
    },
    {
      "id": "api",
      "type": "rectangle",
      "label": "API Gateway",
      "backgroundColor": "#dbe9ff"
    },
    {
      "id": "db",
      "type": "ellipse",
      "label": "Postgres",
      "backgroundColor": "#fce8ff"
    },
    {
      "type": "arrow",
      "start": "user",
      "end": "api",
      "label": "HTTPS"
    },
    {
      "type": "arrow",
      "start": "api",
      "end": "db",
      "label": "SQL"
    }
  ]
}
```

Result (the note's body and metadata are not echoed back):

```json
{
  "path": "Diagrams/Checkout.excalidraw.md",
  "ok": true,
  "element_count": 10,
  "ids": {
    "user": "12dea96f",
    "api": "a033a528",
    "db": "0352a8ac"
  },
  "warnings": []
}
```

`ids` maps your handles to element ids. Handles that are exactly 8 letters/digits are used
as the id; others are hashed to a stable 8-character id and the handle is kept in
`customData.handle`. Every tool that takes an id accepts either.

### Errors list everything at once

```json
{
  "ok": false,
  "written": false,
  "error": "Invalid elements — nothing was written. Fix these and retry:",
  "problems": [
    "elements[2]: unsupported type 'hexagon'. Use rectangle, ellipse, diamond, text, arrow or line",
    "arrow: end 'ghost' not found. Known ids: a"
  ],
  "hint": "Do not hand-write .excalidraw.md JSON. Call excalidraw_get_schema, then excalidraw_create_diagram (any diagram), excalidraw_generate_flowchart, excalidraw_generate_architecture or excalidraw_generate_concept_map; use excalidraw_edit_diagram to change an existing drawing."
}
```

Nothing is written; the AI fixes all problems in one retry.

### Flowcharts

`excalidraw_generate_flowchart(path, title, steps, direction="TB", overwrite=False)` — step
`type` is `start`/`end` (ellipse), `process` (rectangle, default), `decision` (diamond) or `io`;
`next` is a list of step ids or `{"to", "label"}`. A `next` that points back at an earlier step
(the retry loop below) is fine.

```json
{
  "path": "Diagrams/Login",
  "title": "Login",
  "steps": [
    {
      "id": "start",
      "label": "Start",
      "type": "start",
      "next": [
        "creds"
      ]
    },
    {
      "id": "creds",
      "label": "Enter credentials",
      "type": "io",
      "next": [
        "valid"
      ]
    },
    {
      "id": "valid",
      "label": "Valid?",
      "type": "decision",
      "next": [
        {
          "to": "home",
          "label": "yes"
        },
        {
          "to": "err",
          "label": "no"
        }
      ]
    },
    {
      "id": "home",
      "label": "Show dashboard",
      "next": [
        "end"
      ]
    },
    {
      "id": "err",
      "label": "Show error",
      "next": [
        "creds"
      ]
    },
    {
      "id": "end",
      "label": "End",
      "type": "end"
    }
  ]
}
```

### Architecture and concept maps

```json
{
  "path": "Diagrams/Arch",
  "title": "Architecture",
  "layout": "layered",
  "nodes": [
    {
      "id": "web",
      "label": "Web App",
      "type": "service"
    },
    {
      "id": "db",
      "label": "Postgres",
      "type": "database"
    },
    {
      "id": "q",
      "label": "Job queue",
      "type": "queue"
    }
  ],
  "edges": [
    {
      "from": "web",
      "to": "db",
      "label": "SQL"
    },
    {
      "from": "web",
      "to": "q"
    }
  ]
}
```

```json
{
  "path": "Diagrams/Map",
  "central_concept": "Machine Learning",
  "branches": [
    {
      "label": "Supervised",
      "children": [
        "Regression",
        "Classification"
      ]
    },
    {
      "label": "Unsupervised",
      "children": [
        "Clustering"
      ]
    }
  ]
}
```

`generate_architecture` now **fails** on an edge that names an unknown node (it used to skip it
silently). `layout` is `layered` (default, left→right, follows the edges), `grid` or `radial`.

### Reading a drawing

`excalidraw_parse_elements(path, compact=true)` returns what an AI needs before editing:

```json
{
  "path": "Diagrams/Checkout.excalidraw.md",
  "element_count": 10,
  "compressed": false,
  "nodes": [
    {
      "id": "12dea96f",
      "handle": "user",
      "type": "ellipse",
      "label": "User",
      "x": 60,
      "y": 60,
      "w": 180,
      "h": 70.2
    },
    {
      "id": "a033a528",
      "handle": "api",
      "type": "rectangle",
      "label": "API Gateway",
      "x": 328,
      "y": 65.1,
      "w": 180,
      "h": 60
    },
    {
      "id": "0352a8ac",
      "handle": "db",
      "type": "ellipse",
      "label": "Postgres",
      "x": 596,
      "y": 60,
      "w": 180,
      "h": 70.2
    }
  ],
  "connections": [
    {
      "id": "2b8ff7b7",
      "type": "arrow",
      "label": "HTTPS",
      "from": "user",
      "to": "api"
    },
    {
      "id": "bd308b07",
      "type": "arrow",
      "label": "SQL",
      "from": "api",
      "to": "db"
    }
  ],
  "free_text": []
}
```

Without `compact` it returns the raw element list (large).

### Editing

`excalidraw_edit_diagram(path, add, remove_ids, update, direction)`:

- `add` — skeleton items. Arrows may reference **existing** nodes by id/handle. New shapes without
  coordinates are placed in a block below the existing content.
- `remove_ids` — deletes the element, its label and every arrow attached to it.
- `update` — `{id: {"label": …, plus any style key}}`. A longer label grows the shape. Moving
  shapes is not supported (`x`/`y` are rejected).
- It is **all-or-nothing**: the scene is repaired first, the edit applied, the result
  validated, and only then written.

```json
{
  "path": "Diagrams/Checkout.excalidraw.md",
  "add": [
    {
      "id": "cache",
      "type": "rectangle",
      "label": "Redis cache"
    },
    {
      "type": "arrow",
      "start": "api",
      "end": "cache",
      "label": "GET"
    }
  ],
  "update": {
    "db": {
      "label": "Postgres 16",
      "backgroundColor": "#e8f5e9"
    }
  },
  "remove_ids": []
}
```

```json
{
  "path": "Diagrams/Checkout.excalidraw.md",
  "ok": true,
  "ids": {
    "cache": "b0359280"
  },
  "removed": [],
  "warnings": [],
  "repaired_before_edit": [],
  "element_count": 14
}
```

## Safety net for hand-written drawings

If a client writes a drawing through the generic note tools anyway:

| Call on `*.excalidraw.md` | Behaviour |
|---------------------------|-----------|
| `create_note` / `update_note` | Content is parsed, **repaired** (inline labels → bound text, two-way bindings, defaults, relative points, 8-char text ids) and written in the canonical layout. Unreadable content is rejected and nothing is written. |
| `append_note`, `str_replace_note` | Refused — editing JSON as text corrupts it. The error points to `excalidraw_edit_diagram`. |

Accepted content may be bare scene JSON or a full note with a `## Drawing` block. Example repair:

```json
{
  "path": "Raw.excalidraw.md",
  "ok": true,
  "repaired": [
    "rectangle a: filled 18 missing field(s)",
    "rectangle a: converted inline label 'Hello' into a bound text element"
  ],
  "note": "Drawing was written through the generic note tool and normalised. Prefer excalidraw_create_diagram / excalidraw_edit_diagram next time."
}
```

Rejections look like `{"ok": false, "written": false, "error": …, "hint": "Do not hand-write
.excalidraw.md JSON. Call excalidraw_get_schema, …"}`.

The runtime system prompt (`web/app.py::_TOOL_GUIDANCE`) also tells the model not to write drawing JSON.

## Validation and repair

`excalidraw_validate(path, repair=false)` → `{path, ok, issues[], repaired, changes?}`.
`ok` is false only if an *error* remains. `repair=true` fixes everything marked fixable and saves.

| Code | Severity | Meaning | Fixable |
|------|----------|---------|---------|
| `inline_label` | error | shape/arrow carries `text`/`label` (Excalidraw ignores it) | ✅ → bound text |
| `one_way_binding` | error | arrow references a shape that does not list the arrow | ✅ |
| `dangling_binding` | error | binding points at a missing element | ✅ (removed) |
| `orphan_text` / `unbound_text` | error | text's `containerId` missing / container does not list it | ✅ |
| `bad_points` | error | arrow `points` not ≥2 `[x, y]` pairs | ✅ |
| `bad_geometry`, `bad_text` | error | `x/y/width/height` or `text` not usable | partly |
| `duplicate_id`, `missing_id` | error | | ✅ (new id) |
| `not_object`, `no_elements` | error | not a scene | ❌ |
| `points_origin` | warning | first point not `[0, 0]` | ✅ (re-based; absolute points that duplicate `x, y` are detected) |
| `missing_defaults` | warning | `seed`, `version`, … missing | ✅ |
| `text_id_length` | warning | text id is not 8 alphanumerics | ✅ (re-keyed) |
| `dangling_bound_ref` | warning | `boundElements` lists a missing element | ✅ |
| `unknown_type`, `bad_type` | warning | left untouched | — |

Unknown element types, images, frames and free-draw strokes are **kept as they are**.

## Files

Written files follow the layout the Obsidian plugin itself uses:

````
---
excalidraw-plugin: parsed
tags: [excalidraw, diagram]
title: "…"
---
==⚠ Switch to EXCALIDRAW VIEW … ⚠==

# <title>

# Excalidraw Data

## Text Elements
<label> ^<8-char id>

%%
## Drawing
```json
{ … scene … }
```
%%
````

- **Reading** supports both ```` ```json ```` and ```` ```compressed-json ```` (the plugin's default).
  `lz_decompress_base64` is a port of LZString and is tested against the real JS library, including
  non-BMP characters.
- **Editing** rewrites only the `## Text Elements` and `## Drawing` sections: frontmatter, any markdown
  above `# Excalidraw Data` and `## Embedded Files` (images) are preserved byte for byte. The drawing is
  written uncompressed; Obsidian re-compresses it on its next save if that setting is on.

## Layout and routing

- **Layered** (default): longest-path layering with barycentre ordering to reduce crossings;
  cycles are tolerated (back-edges ignored when layering). `direction` `TB` or `LR`. In `LR`
  the gap between layers widens (up to 280 px) so wide arrow labels fit on their arrow.
- **Grid** / **radial** via `layout`. Unconnected shapes: ≤ 6 → one row, otherwise a grid.
- **Arrows** run border-to-border (8 px gap, matching the binding `gap`). A and B arrows in
  opposite directions are offset 12 px so they do not overlap. If a straight arrow would cross
  another shape it becomes a curved arrow (3 points, `roundness: {"type": 2}`) bent around the obstacle.
- **Sizing**: labels are wrapped (~24 chars) and shapes grow to fit; text width is estimated at
  0.6 em per character (exact for the default monospace font, with slack for proportional ones).

## Limitations and assumptions

- **Not exercised in a running Obsidian during development.** Output is covered by structural
  validation, round-trip tests, rendering to images and the plugin's documented file layout. If a
  drawing misbehaves, run `excalidraw_validate` and keep the file for a bug report.
- The 8-character text-id rule is based on the plugin's file format (confidence: medium); the engine
  always emits 8 characters, which is valid either way.
- Arrow labels are assumed to mask the line behind them (Excalidraw's behaviour); a renderer that
  does not will draw the line through the label.
- Arrows connect shapes only (an arrow to a free `text` is drawn but not bound); no self-loops; no
  elbow arrows; the default font is Cascadia (`fontFamily` 3) — set `fontFamily` per element to change it.
- `edit_diagram` cannot move shapes; it can add, remove, relabel and restyle.

### Excalidraw CLI

The Excalidraw plugin's CLI for local AI agents (needs a running Obsidian 1.12.2+) is **not** used.
The failures it could address were fixed server-side, and the MCP must keep working with Obsidian
closed. It could later serve as an optional export (PNG/SVG) or verification step.

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Labels missing in Obsidian | The drawing was written by hand with inline `text`. Run `excalidraw_validate(repair=true)`. |
| Arrows detach when dragging | `one_way_binding` — same fix. |
| `Invalid elements — nothing was written` | Read `problems`; each names the element and, for unknown ids, lists the known ones. |
| `create_note` returned `ok: false` | The content was not a readable scene; use `excalidraw_create_diagram`. |
| `append_note` refused | Use `excalidraw_edit_diagram` / `excalidraw_add_annotation`. |
| Drawing is huge in the chat | Use `excalidraw_parse_elements(compact=true)`. |

## Testing

`_test_/unit/plugins/test_excalidraw_scene.py` (engine, LZ-string vs real JS output, layout,
routing regressions), `test_excalidraw_service.py` (service against a temp vault, guard, edit
atomicity) and `test_excalidraw_tools.py` (tool registration, guard through `create_note`).
