# Obsidian MCP

A production-grade [Model Context Protocol](https://modelcontextprotocol.io) server
that connects Claude Desktop (and any compatible LLM) directly to your Obsidian vault.

Supports **Dataview · Tasks · Templater · Excalidraw · Omnisearch** — generating
plugin-native markdown that Obsidian can read and render without any extra configuration.

---

## Table of contents

1. [Requirements](#requirements)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Connect to Claude Desktop](#connect-to-claude-desktop)
5. [Connect to other LLMs](#connect-to-other-llms)
6. [Web UI](#web-ui)
7. [Obsidian Local REST API plugin (optional)](#obsidian-local-rest-api-plugin)
8. [AI Rules system](#ai-rules-system)
9. [Plugin reference](#plugin-reference)
10. [Vault adapter modes](#vault-adapter-modes)
11. [Permission profiles](#permission-profiles)
12. [Troubleshooting](#troubleshooting)
13. [Developer docs](#developer-docs)

---

## Requirements

| Tool | Minimum version |
|------|----------------|
| Python | **3.11** |
| uv (recommended) or pip | any recent |
| Obsidian | any version (vault is plain markdown) |
| Claude Desktop | any current release |

---

## Installation

### Option A — uv (recommended)

```bash
# 1. Clone the repository
git clone https://github.com/your-org/obsidian-mcp.git
cd obsidian-mcp

# 2. Create a virtual environment and install
uv venv
uv pip install -e ".[dev]"

# 3. Copy and edit the environment file
cp .env.example .env
```

### Option B — pip

```bash
git clone https://github.com/your-org/obsidian-mcp.git
cd obsidian-mcp
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

---

## Configuration

Edit `.env` in the project root:

```env
# ── Required ────────────────────────────────────────────────────────
OBSIDIAN_MCP_VAULT_PATH=/absolute/path/to/your/ObsidianVault

# ── Optional: server identity ───────────────────────────────────────
OBSIDIAN_MCP_SERVER_NAME=obsidian-mcp
OBSIDIAN_MCP_LOG_LEVEL=INFO          # DEBUG | INFO | WARNING | ERROR

# ── Optional: permission profile ───────────────────────────────────
# read_only  — no writes at all
# safe_write — create/update/append (default, recommended)
# admin      — includes delete, move, rename
OBSIDIAN_MCP_PERMISSION_PROFILE=safe_write

# ── Optional: vault adapter ─────────────────────────────────────────
# auto       — probe REST API first, fall back to direct file access
# rest       — use REST API only (requires plugin)
# filesystem — direct file access only (default when no API key set)
OBSIDIAN_MCP_ADAPTER_MODE=auto
OBSIDIAN_MCP_ADAPTER_API_KEY=        # paste your REST API key here
OBSIDIAN_MCP_ADAPTER_HOST=127.0.0.1
OBSIDIAN_MCP_ADAPTER_PORT=27123

# ── Optional: Web UI ────────────────────────────────────────────────
OBSIDIAN_MCP_WEB_HOST=127.0.0.1
OBSIDIAN_MCP_WEB_PORT=8765

# ── Optional: Templater ─────────────────────────────────────────────
OBSIDIAN_MCP_TEMPLATES_FOLDER=Templates
```

> **Windows paths** — use forward slashes or escape backslashes:
> `OBSIDIAN_MCP_VAULT_PATH=C:/Users/Alice/Documents/MyVault`

---

## Connect to Claude Desktop

Claude Desktop connects over **stdio** (the MCP standard for local servers).

### Step 1 — Find the config file

| OS | Location |
|----|----------|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

### Step 2 — Add the server block

Open the file (create it if it doesn't exist) and add:

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/obsidian-mcp",
        "run",
        "obsidian-mcp"
      ],
      "env": {
        "OBSIDIAN_MCP_VAULT_PATH": "/absolute/path/to/your/ObsidianVault"
      }
    }
  }
}
```

**Using pip / virtualenv instead of uv:**

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "/absolute/path/to/obsidian-mcp/.venv/bin/python",
      "args": ["-m", "obsidian_mcp"],
      "env": {
        "OBSIDIAN_MCP_VAULT_PATH": "/absolute/path/to/your/ObsidianVault"
      }
    }
  }
}
```

**Windows (uv):**

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\Alice\\obsidian-mcp",
        "run",
        "obsidian-mcp"
      ],
      "env": {
        "OBSIDIAN_MCP_VAULT_PATH": "C:\\Users\\Alice\\Documents\\MyVault"
      }
    }
  }
}
```

### Step 3 — Restart Claude Desktop

Quit and relaunch Claude Desktop. You should see the 🔌 tools icon in the
input bar. Click it to verify the `obsidian` server is listed.

### Step 4 — Test it

Ask Claude:

> "List the notes in my vault" — calls `list_files`
> "Create a concept note about Docker networking" — calls `create_note`
> "Build a Dataview dashboard for my Projects folder" — calls `dataview_build_dashboard`

---

## Connect to other LLMs

### Open WebUI / Ollama

Open WebUI supports MCP servers via its tool-use settings.

1. In Open WebUI → **Admin → Tools → Add Tool**
2. Set **Type** to `MCP`
3. Set **Command** to the same `uv run obsidian-mcp` command above
4. Save and enable for your model

### Continue.dev (VS Code / JetBrains)

Add to `~/.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "obsidian",
      "command": "uv",
      "args": ["--directory", "/path/to/obsidian-mcp", "run", "obsidian-mcp"],
      "env": {
        "OBSIDIAN_MCP_VAULT_PATH": "/path/to/vault"
      }
    }
  ]
}
```

### LM Studio (local models)

LM Studio 0.3.6+ supports MCP. In **Settings → MCP Servers → Add**:

- **Name:** `obsidian`
- **Command:** `uv --directory /path/to/obsidian-mcp run obsidian-mcp`
- **Environment:** `OBSIDIAN_MCP_VAULT_PATH=/path/to/vault`

### Cline / Roo Code (VS Code extension)

In the Cline extension settings → **MCP Servers → Add Server**:

```json
{
  "obsidian": {
    "command": "uv",
    "args": ["--directory", "/path/to/obsidian-mcp", "run", "obsidian-mcp"],
    "env": {
      "OBSIDIAN_MCP_VAULT_PATH": "/path/to/vault"
    }
  }
}
```

### OpenAI-compatible APIs (GPT-4o, etc.)

OpenAI's Responses API supports MCP via HTTP. Run the Web UI server which
exposes all tools as REST endpoints, then point your OpenAI client at it.

```bash
obsidian-mcp-web   # starts at http://127.0.0.1:8765
```

```python
from openai import OpenAI

client = OpenAI()
response = client.responses.create(
    model="gpt-4o",
    tools=[{
        "type": "mcp",
        "server_url": "http://127.0.0.1:8765",
        "server_label": "obsidian",
    }],
    input="List my open tasks",
)
```

---

## Web UI

The Web UI runs on `http://127.0.0.1:8765` and gives you a browser-based
interface for all MCP tools — no Claude Desktop required.

```bash
obsidian-mcp-web
# or:
uv run obsidian-mcp-web
```

Open `http://localhost:8765` in your browser.

### Web UI views

| View | What it does |
|------|-------------|
| **Notes** | Browse, read, and edit vault notes |
| **Search** | Fuzzy full-text search |
| **Knowledge** | Build MOCs, create atomic notes |
| **Graph** | Visualise vault link relationships |
| **Dataview** | Build dashboards, inspect fields, generate queries |
| **Tasks** | Browse, create, complete Tasks-plugin tasks |
| **Templater** | List, preview, apply, and create templates |
| **Excalidraw** | Generate architecture and concept-map diagrams; install Script Engine tools |
| **Kanban** | Create and manage Kanban-plugin boards, lanes, and cards |
| **Omnisearch** | Audit and optimise note discoverability |
| **AI Rules** | Set behavioural rules the AI must follow |
| **Docs** | Plugin syntax reference and MCP tool index |
| **Permissions** | View/change permission profile |
| **Settings** | REST API key, server info |

---

## Obsidian Local REST API plugin

By default the MCP server reads and writes `.md` files directly from disk
(no Obsidian instance required). If you want live sync with a running Obsidian
instance, install the **Local REST API** plugin.

### Install the plugin

1. In Obsidian → **Settings → Community plugins → Browse**
2. Search for **"Local REST API"**
3. Install and enable it
4. Go to **Settings → Local REST API**
5. Copy the **API Key**

### Configure the MCP server

**Option A — Environment file (.env):**

```env
OBSIDIAN_MCP_ADAPTER_MODE=auto
OBSIDIAN_MCP_ADAPTER_API_KEY=your-key-here
OBSIDIAN_MCP_ADAPTER_HOST=127.0.0.1
OBSIDIAN_MCP_ADAPTER_PORT=27123
```

**Option B — Web UI Settings page:**

1. Open `http://localhost:8765`
2. Click **Settings** in the sidebar
3. Paste your API key under "Obsidian Local REST API"
4. Click **Test connection** to verify
5. Click **Save connection**

The server will probe the REST API at startup. If Obsidian is running and the
key is valid it uses the live API; otherwise it falls back to direct file access.

---

## AI Rules system

The AI Rules system lets you define hard behavioural constraints that are
injected as a system prompt into every MCP session. The AI reads these before
any tool call.

### Edit rules in the Web UI

1. Open the Web UI → **AI Rules**
2. Write one rule per line in the text area
3. Use the preset buttons to append common rule sets:
   - 🖥️ **HomeLab vault** — folder conventions, tags, template requirements
   - 🧩 **Zettelkasten** — atomic notes, linking discipline, tag sparsity
   - ✅ **GTD workflow** — inbox capture, task formatting, review cadence
   - 🔒 **Safe mode** — confirm-before-write, read-only by default
4. Click **Save rules**
5. Click **System prompt preview** to see exactly what gets injected

### Edit rules manually

Rules are stored in `.vault-rules` in the project root (plain text, one rule per line):

```
Never delete notes without explicit user confirmation.
Always add frontmatter to new notes.
Do not modify notes inside Archive/ unless asked.
When creating tasks, always include a due date.
Tag all project notes with the project name.
```

Lines starting with `#` are treated as comments and ignored.

### How rules are injected

At startup `__main__.py` reads `.vault-rules` and builds:

```
You are an Obsidian vault assistant with access to MCP tools...

VAULT RULES — You MUST follow these rules in every action:
  1. Never delete notes without explicit user confirmation.
  2. Always add frontmatter to new notes.
  ...

Only deviate from these rules if the user explicitly overrides one.
```

This string is passed as `instructions=` to `FastMCP`, which MCP-compatible
clients surface as the server-level system prompt.

---

## Plugin reference

### Dataview

Dataview turns your notes into a queryable database. The MCP generates
`TABLE`, `TASK`, and `LIST` query blocks, adds `key:: value` inline fields,
and builds full dashboard notes.

**Key concepts:**
- Frontmatter fields and `key:: value` inline fields are queryable
- `FROM "folder"` scopes queries; `FROM #tag` filters by tag
- `WHERE`, `SORT`, `LIMIT`, `GROUP BY` work like SQL
- The MCP generates static blocks; Dataview renders them live in Obsidian

**MCP tools:** `dataview_extract_fields`, `dataview_add_inline_fields`,
`dataview_build_dashboard`, `dataview_table_query`, `dataview_task_query`

### Tasks

The Tasks plugin parses emoji-annotated checkbox lines:

```
- [ ] Review PR 📅 2026-06-20 🔼
- [ ] Daily standup 🔁 every weekday ⏳ 2026-06-14
- [x] Setup vault ✅ 2026-06-10
```

**Emoji reference:**
| Emoji | Meaning |
|-------|---------|
| 📅 | Due date |
| ⏳ | Scheduled date |
| 🛫 | Start date |
| ✅ | Done date |
| 🔁 | Recurrence rule |
| ⏫ 🔼 🔽 ⏬ | Priority (highest → lowest) |

**MCP tools:** `tasks_list`, `tasks_aggregate`, `tasks_create`,
`tasks_complete`, `tasks_create_note`

### Templater

Templater processes `<% %>` expressions when a note is opened in Obsidian.
The MCP resolves static calls at generation time and preserves dynamic blocks.

**Resolved by MCP (at generation time):**
- `tp.date.now()` → today's ISO date
- `tp.date.now("YYYY-MM-DD")` → today's date
- `tp.file.title` → the note's title

**Preserved for Templater (resolved when opened in Obsidian):**
- `<%* js code %>` — any JavaScript block
- `tp.system.prompt()` — user input dialog
- `tp.file.cursor()` — cursor placement

**Template types:** `concept` · `project` · `journal` · `meeting` · `reference` · `system`

**MCP tools:** `templater_list_templates`, `templater_read_template`,
`templater_apply`, `templater_create_template`

### Excalidraw

#### Prerequisites

1. Install the [Excalidraw plugin](https://github.com/zsviczian/obsidian-excalidraw-plugin)
   from Obsidian's Community Plugins browser and enable it.

2. Set the **Script Engine folder** so installed scripts are discovered:
   - Open **Settings → Excalidraw → Script Engine**
   - Set the folder to `Excalidraw/Scripts` (must match the `scripts_folder`
     argument used when calling `excalidraw_install_scripts`; default matches)

3. Ask the AI to install the bundled scripts once:
   > *"Install the Excalidraw scripts into my vault"*

   This calls `excalidraw_install_scripts` and writes 18 Script Engine files
   to `Excalidraw/Scripts/`. They appear immediately in Obsidian's command
   palette as **Excalidraw Script: \<name\>** and can be assigned hotkeys.

#### What the AI does vs. what scripts do

The MCP and the Script Engine serve different roles and are **not** interchangeable:

| Responsibility | How |
|----------------|-----|
| Generate a new diagram from scratch | AI calls `excalidraw_generate_architecture` or `excalidraw_generate_concept_map` — produces a correct `.excalidraw.md` file with bound arrows |
| Embed a diagram inline in a note | AI calls `excalidraw_embed_in_note` — inserts `![[drawing.excalidraw.md]]` into any markdown note |
| Install scripts for the user | AI calls `excalidraw_install_scripts` |
| Run **Auto Layout** on a diagram | User selects elements, runs **Excalidraw Script: Auto Layout** from the command palette |
| Add a process step interactively | User runs **Excalidraw Script: Add Next Step in Process** |
| Write a custom automation | AI calls `excalidraw_write_script` with authored JavaScript |

The AI cannot *execute* scripts — they run inside Obsidian's JavaScript
runtime, which the MCP has no access to. The scripts are a user productivity
layer for interactive editing after the AI generates the initial diagram.

#### Bundled scripts (installed via `excalidraw_install_scripts`)

**Layout & structure**
- **Auto Layout** — ELK-powered automatic layout (layered / radial / tree). Requires internet on first run.
- **Mindmap Builder** — Full interactive mindmap environment with sidepanel UI, keyboard shortcuts, auto-layout, and colour coding.
- **Mindmap format** — Auto-format a left-to-right mindmap; re-spaces nodes and aligns branches.
- **Mindmap connector** — Connect selected nodes with mindmap-style right-angle lines.
- **Elbow connectors** — Convert selected arrows to right-angle elbow connectors.

**Drawing workflow**
- **Connect elements** — Connect two selected objects with a properly bound arrow matching source style.
- **Box Selected Elements** — Wrap the selection in a bounding rectangle (prompts for padding).
- **Box Each Selected Groups** — Add an individual box around each selected group.
- **Add Next Step in Process** — Prompt for a label, create a sticky-note step, auto-connect with an arrow.
- **Set Dimensions** — Set exact x / y / width / height on the largest selected element.
- **Concatenate lines** — Merge two arrows or lines into one.

**Conversion & editing**
- **Convert freedraw to line** — Convert freehand drawings to editable polylines.
- **Convert selected text elements to sticky notes** — Make text elements wrappable.
- **Add Connector Point** — Add a bullet-point circle to each selected text element.
- **Copy Selected Element Styles to Global** — Copy stroke/fill/font to the global toolbar.

**Vault linking**
- **Add Link to Existing File and Open** — Attach a wikilink to a selected element pointing to a vault file.
- **Add Link to New Page and Open** — Create a new note or drawing and attach a link to a selected element.
- **Deconstruct selected elements into new drawing** — Move selected elements to a new file and replace them with an embedded reference.

#### Node types for architecture diagrams

| Type | Shape | Colour |
|------|-------|--------|
| `service` | Rectangle | Blue |
| `database` | Ellipse | Purple |
| `queue` | Rectangle | Yellow |
| `external` | Rectangle | Green |
| `user` | Ellipse | Orange |
| `container` | Rectangle | Grey |

**Layouts:** `layered` (left-to-right) · `grid` · `radial`

#### MCP tools

| Tool | Description |
|------|-------------|
| `excalidraw_generate_architecture` | Generate a diagram from explicit node/edge spec |
| `excalidraw_generate_concept_map` | Generate a radial concept map |
| `excalidraw_parse_elements` | Read element list from an existing drawing |
| `excalidraw_add_annotation` | Add a floating text element to a drawing |
| `excalidraw_embed_in_note` | Insert `![[drawing]]` transclusion into a markdown note |
| `excalidraw_install_scripts` | Install bundled Script Engine files into the vault |
| `excalidraw_list_bundled_scripts` | List all bundled scripts with descriptions |
| `excalidraw_write_script` | Author and save a custom JavaScript Script Engine file |

### Kanban

#### Prerequisites

Install the [Kanban plugin](https://github.com/mgmeyers/obsidian-kanban)
from Obsidian's Community Plugins browser and enable it. No further
configuration is required — boards work as soon as the file is created.

#### File format

A Kanban board is a single `.md` file with `kanban-plugin: basic` in its
frontmatter. Each `##` heading is a lane (left-to-right column order);
each checkbox line under a lane is a card:

```markdown
---
kanban-plugin: basic
title: Homelab Sprint
---

## Backlog

- [ ] Migrate Plex to new NAS 🔼

## In Progress

- [ ] Set up Proxmox cluster 📅 2026-07-01 ⏫

## Done

**Complete**
- [x] Configure Pi-hole ✅ 2026-06-18
```

Cards use the same emoji syntax as the **Tasks** plugin (📅 due, ⏳
scheduled, 🔼/⏫/🔽/⏬ priority, 🔁 recurrence), so cards created here are
also visible to `tasks_aggregate` and any Dataview `TASK` query — there's
no separate card format to learn. A lane with a `**Complete**` marker
line is treated as the board's done column.

#### MCP tools

| Tool | Description |
|------|-------------|
| `kanban_create_board` | Create a full board with lanes and cards in one call |
| `kanban_create_simple_board` | Scaffold an empty board with just lane headings |
| `kanban_add_card` | Add a card to a lane (creates the lane if missing) |
| `kanban_move_card` | Move a card to a different lane, preserving its dates/priority |
| `kanban_complete_card` | Mark a card's checkbox done in place (does not move lanes) |
| `kanban_read_board` | Parse a board into structured lanes and cards |
| `kanban_lane_summary` | Quick card-count-per-lane summary |

Note: completing a card does not automatically move it to a "Done"
lane — call `kanban_move_card` afterwards if that's the desired result.

### Omnisearch

Omnisearch indexes note filenames, frontmatter, and body content.
The MCP audits discoverability and suggests aliases and keywords.

**What makes a note discoverable:**
- Descriptive filename with spaces
- `title:` in frontmatter (weighted highest)
- `aliases:` list with alternative names
- Hierarchical tags (`#home-lab/networking`)
- Key terms repeated naturally in body

**MCP tools:** `omnisearch_suggest_aliases`, `omnisearch_add_aliases`,
`omnisearch_suggest_keywords`, `omnisearch_find_poorly_indexed`,
`omnisearch_optimise_note`, `omnisearch_bulk_optimise`

---

## Vault adapter modes

| Mode | When to use | Obsidian required? |
|------|-------------|-------------------|
| `auto` | Default — probes REST API, falls back to filesystem | No |
| `rest` | You always want live sync with running Obsidian | Yes |
| `filesystem` | Server-only, no Obsidian instance | No |

Set via `OBSIDIAN_MCP_ADAPTER_MODE` in `.env`.

---

## Permission profiles

| Profile | Allowed operations |
|---------|--------------------|
| `read_only` | Read, search, list, suggest (zero writes) |
| `safe_write` | All reads + create, update, append, all plugin writes **(default)** |
| `admin` | All of above + delete, move, rename |

Change at runtime via the Web UI **Permissions** view or the topbar dropdown.

---

## Troubleshooting

### Claude Desktop shows no tools

1. Check the config file path is correct for your OS
2. Verify the `command` path — run it manually in a terminal:
   ```bash
   uv --directory /path/to/obsidian-mcp run obsidian-mcp
   ```
   It should start without error (no output is correct — it awaits stdio).
3. Check `OBSIDIAN_MCP_VAULT_PATH` points to an existing directory.
4. Restart Claude Desktop fully (Quit, not just close the window).

### "Vault path does not exist"

The path in `OBSIDIAN_MCP_VAULT_PATH` must be an absolute path to an
existing directory. Relative paths are not supported.

### REST API connection fails

1. Confirm Obsidian is running with the Local REST API plugin enabled
2. Check **Settings → Local REST API** in Obsidian for the correct port
3. Click **Test connection** in the Web UI Settings page
4. Ensure no firewall blocks `127.0.0.1:27123`
5. Set `OBSIDIAN_MCP_ADAPTER_MODE=filesystem` to bypass REST entirely

### Permission denied errors

Your current profile doesn't allow the requested action. Change the profile
in the Web UI topbar dropdown or set `OBSIDIAN_MCP_PERMISSION_PROFILE=admin`
in `.env` for full access.

### Dataview queries not rendering

The MCP generates static markdown query blocks. Rendering requires the
Dataview plugin to be installed and enabled in Obsidian. The blocks are
correct markdown even without the plugin — they just display as code fences.

### Tasks not showing priority / due date

Ensure emoji fields come **after** the task description text. The Tasks plugin
parses right-to-left. Example of correct order:

```
- [ ] Task text 🔁 every week ⏳ 2026-06-14 📅 2026-06-20 🔼
```

---

## Developer docs

Internal technical references are in the [`docs/`](docs/) folder.

| Doc | What it covers |
|-----|---------------|
| [docs/backlink-index.md](docs/backlink-index.md) | `BacklinkIndex` architecture, cold-start persistence, watchdog live updates, thread safety, performance, logging reference |

---

## Project structure

```
obsidian-mcp/
├── docs/                        ← developer technical references
│   ├── README.md                ← docs index
│   └── backlink-index.md        ← BacklinkIndex architecture & persistence
├── src/obsidian_mcp/
│   ├── __init__.py
│   ├── __main__.py              ← entry points (MCP + Web UI)
│   ├── config.py                ← settings (env vars)
│   ├── server.py                ← FastMCP factory
│   ├── permissions.py           ← permission profiles
│   ├── errors.py                ← typed error classes
│   ├── logging.py               ← structured logging
│   ├── adapters/                ← vault I/O backends
│   │   ├── base.py
│   │   ├── filesystem.py        ← direct .md file access + exclusion helpers
│   │   ├── rest_api.py          ← Obsidian Local REST API
│   │   └── auto.py              ← probes and selects adapter
│   ├── vault/                   ← core vault operations
│   │   ├── service.py           ← VaultService (wires BacklinkIndex)
│   │   ├── index.py             ← BacklinkIndex + watchdog handler
│   │   ├── paths.py
│   │   └── metadata.py
│   ├── knowledge/               ← MOC, graph, PARA, duplicates
│   │   ├── service.py
│   │   └── analysis.py
│   ├── plugins/                 ← plugin-aware services
│   │   ├── dataview.py
│   │   ├── tasks.py
│   │   ├── templater.py
│   │   ├── excalidraw.py
│   │   ├── kanban.py
│   │   └── omnisearch.py
│   ├── tools/                   ← MCP tool registrations
│   │   ├── core.py
│   │   ├── knowledge.py
│   │   └── plugins.py
│   └── web/                     ← local Web UI
│       ├── app.py
│       └── static/
│           ├── index.html
│           ├── styles.css
│           └── app.js
├── tests/
├── .env.example
├── .vault-rules                 ← AI behavioural rules (auto-created)
├── pyproject.toml
└── README.md
```
