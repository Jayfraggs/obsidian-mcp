# Setup Wizard & Server Launcher — Developer Reference

Last updated: 2026-09-20

## Overview

Two scripts at the repo root provide a GUI-based setup and runtime experience
for non-developer users:

| File | Purpose |
|------|---------|
| `setup_wizard.py` | One-time GUI setup wizard — installs deps, writes `.env`, merges Claude Desktop config, creates shortcut |
| `server_launcher.py` | Ongoing server launcher — system tray icon + openable status panel |

Both scripts are self-bootstrapping: they install their own GUI dependencies
(`customtkinter`, `pystray`, `Pillow`) via pip on first run if they're missing.
The only hard requirement is **Python 3.11+**.

---

## Architecture

### setup_wizard.py

```
SetupWizard (ctk.CTk)
├── _build_sidebar()         — step indicator (7 steps)
├── _build_content_area()    — scrollable page + nav buttons
├── _show_step(index)        — renders a page, updates sidebar state
│
├── Pages
│   ├── _page_welcome        — Python + uv status badges
│   ├── _page_prerequisites  — required/suggested plugin cards + ack checkbox
│   ├── _page_rest_api       — step-by-step Local REST API guide
│   ├── _page_configure      — all .env fields with live field toggling
│   ├── _page_environment    — .env preview (read-only textbox)
│   ├── _page_install        — threaded install runner with live log
│   └── _page_done           — summary, copy command, launch button
│
└── Utility functions (module-level, all testable without GUI)
    ├── get_os()
    ├── get_claude_desktop_config_path()
    ├── get_project_root()
    ├── get_env_path()
    ├── get_uv_exe()
    ├── write_env(fields)
    ├── merge_claude_desktop_config(command, env_vars)
    ├── install_uv()
    ├── run_uv_sync(log_callback)
    └── create_desktop_shortcut(server_mode)
```

The GUI class (`SetupWizard`) holds all state as `ctk.StringVar` and
`ctk.BooleanVar` instances in `self.fields` and `self.booleans`. Pages
bind directly to these vars — no intermediate state dict needed.

The install step (`_page_install` → `_run_install`) runs in a daemon thread
so the GUI stays responsive during `uv sync`. It calls `self.after(0, ...)` to
push UI updates back to the main thread safely.

### server_launcher.py

```
TrayController
├── ServerProcess            — subprocess lifecycle manager
│   ├── start()              — spawns uv run obsidian-mcp
│   ├── stop()               — terminate + kill fallback
│   ├── restart()            — stop + start
│   ├── _stream_output()     — daemon thread: reads stdout → on_log callback
│   └── _watch_exit()        — daemon thread: waits for exit → on_status_change
│
├── StatusPanel (ctk.CTkToplevel)
│   ├── append_log(msg)      — thread-safe log append (via self.after)
│   ├── update_status(str)   — thread-safe status badge + button state update
│   └── _on_close()          — withdraw instead of destroy (tray keeps app alive)
│
└── pystray.Icon             — system tray icon
    ├── Right-click menu: Start / Stop / Restart / Open Status Panel / Quit
    ├── Icon colour: purple=running, grey=stopped, red=error
    └── Default action (double-click): open status panel
```

**Thread model:**

```
Main thread         — tkinter event loop (ctk root)
Tray thread         — pystray icon (daemon)
Stream thread       — reads server stdout line-by-line (daemon)
Watch thread        — blocks on proc.wait() to detect exit (daemon)
```

All callbacks from non-main threads go through `self._root.after(0, fn)` or
`panel.after(0, fn)` — never update tkinter widgets directly from a background thread.

The hidden `ctk.CTk()` root in `TrayController` is required because
`ctk.CTkToplevel` (the status panel) must have a root window to attach to,
even if that root is never shown.

---

## Module-level function reference

### setup_wizard.py

#### `get_os() -> str`
Returns `"windows"`, `"mac"`, or `"linux"` based on `platform.system()`.
Linux is the fallthrough for any unrecognised system.

#### `get_claude_desktop_config_path() -> Path | None`
Returns the OS-specific path to `claude_desktop_config.json`:
- Windows: `%APPDATA%/Claude/claude_desktop_config.json`
- Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Linux: `$XDG_CONFIG_HOME/Claude/claude_desktop_config.json` (falls back to `~/.config`)

#### `get_project_root() -> Path`
Returns the directory containing `setup_wizard.py`. Because the script lives
at the repo root, this is always the repo root — used for `uv --directory`.

#### `get_env_path() -> Path`
Returns `get_project_root() / ".env"`.

#### `get_uv_exe() -> str | None`
`shutil.which("uv")` — returns the full path if found, `None` if not.

#### `write_env(fields: dict[str, str]) -> None`
Writes a `.env` file to `get_env_path()`. Includes a generated-by header and
timestamp. Overwrites any existing `.env` — no merge; the wizard is the source
of truth.

#### `merge_claude_desktop_config(server_command: list[str], env_vars: dict[str, str]) -> tuple[bool, str]`
Reads the existing Claude Desktop config (if any), merges the `obsidian-mcp`
entry under `mcpServers`, and writes atomically via `.tmp` → rename.

Preserves all existing `mcpServers` entries. Only `obsidian-mcp` is
overwritten. Returns `(True, path_str)` on success, `(False, error_msg)` on failure.

If the config file does not exist, it is created with the correct directory
structure.

#### `install_uv() -> tuple[bool, str]`
Runs the official uv installer:
- Windows: `powershell -Command "irm https://astral.sh/uv/install.ps1 | iex"`
- Mac/Linux: `sh -c "curl -LsSf https://astral.sh/uv/install.sh | sh"`

Returns `(True, stdout)` on success, `(False, stderr)` on failure.
Timeout: 120 seconds.

#### `run_uv_sync(log_callback: Callable[[str], None]) -> tuple[bool, str]`
Runs `uv sync` in `get_project_root()`. Streams stdout line-by-line to
`log_callback` so the wizard's log box updates in real time.
Returns `(returncode == 0, full_output)`.

#### `create_desktop_shortcut(server_mode: bool = False) -> bool`
Creates a desktop shortcut pointing to `server_launcher.py` (if `server_mode=True`)
or `setup_wizard.py` (if False). Platform-specific:
- Windows: `.lnk` via PowerShell `WScript.Shell`
- Mac: executable `.command` shell script
- Linux: `.desktop` entry file (XDG)

Returns `True` on success, `False` on any exception (non-fatal — wizard
reports it but continues).

---

### server_launcher.py

#### `build_server_command() -> list[str]`
Returns `[uv_exe, "--directory", str(project_root), "run", "obsidian-mcp"]`.
Falls back to `"uv"` string if `shutil.which("uv")` returns nothing (uv was
just installed and PATH hasn't refreshed).

#### `_make_tray_image(color: str) -> PIL.Image`
Draws a 64×64 RGBA circle with an "M" label — no image file assets required.
Called each time the server status changes to re-colour the icon.

#### `ServerProcess`

```python
ServerProcess(
    on_log: Callable[[str], None],
    on_status_change: Callable[[str], None],
)
```

Manages a single `subprocess.Popen` instance. Status values: `"stopped"`,
`"running"`, `"error"`.

- `start()` — acquires `_lock`, checks `_proc.poll()`, spawns, sets status,
  starts stream and watch threads.
- `stop()` — acquires `_lock`, calls `terminate()`, waits up to 5 seconds,
  kills if still running.
- `restart()` — `stop()` + 500ms sleep + `start()`.
- `is_running()` — `_proc is not None and _proc.poll() is None`.

Log messages include a `[HH:MM:SS]` timestamp prefix.

**Concurrency note:** `_lock` only protects the start/stop critical sections.
The stream and watch threads run concurrently without the lock. Status
transitions are always driven by the watch thread on exit, or by `stop()`.
There is no race-free way to guarantee `status == "running"` immediately after
`start()` returns without a synchronisation primitive in the caller — see the
test for how to handle this.

#### `StatusPanel`

`ctk.CTkToplevel` — shown on double-click or from the tray menu.
`_on_close` withdraws rather than destroys so the tray keeps the app alive.
Call `panel.show()` to re-surface it.

All public methods (`append_log`, `update_status`) are thread-safe via
`self.after(0, ...)`.

Log lines are trimmed to `LOG_MAXLINES = 300` — oldest lines are deleted
when the buffer exceeds this.

#### `TrayController`

Owns the hidden root, the tray icon, and the status panel instance.
`run()` blocks until `_quit()` is called (either from the tray menu or
programmatically).

`_open_panel` always runs on the tkinter thread via `self._root.after(0, ...)`.
It creates `StatusPanel` on first call and calls `panel.show()` on subsequent calls.

---

## Adding a new wizard step

1. Add the step name to the `STEPS` list in `setup_wizard.py`.
2. Write a `_page_<name>(self)` method on `SetupWizard`.
3. Add it to the `pages` list inside `_show_step` at the correct index.
4. If the step requires validation before the user can proceed, add a check
   in `_validate_step` keyed on the step index.

Steps that collect fields should add vars to `_setup_state_vars` and
include them in `_build_env_dict` or `_build_server_command` as appropriate.

---

## Testing

Tests live at `_test_/unit/test_setup_wizard.py`. They mock all GUI
modules (`customtkinter`, `pystray`, `tkinter`) at import time so tests
run headlessly with no display required.

The test file covers:

| Category | Count |
|----------|-------|
| OS detection | 4 |
| Config path resolution (per OS) | 3 |
| `.env` write | 3 |
| Claude Desktop JSON merge | 5 |
| Server command construction | 2 |
| `ServerProcess` lifecycle | 6 |
| Desktop shortcut (per OS) | 3 |
| `install_uv` | 3 |
| `run_uv_sync` | 2 |
| **Total** | **31** |

Run with:

```bash
pytest _test_/unit/test_setup_wizard.py -v
```

The `test_server_start_sets_running` test uses a threading event to avoid a
race condition between `ServerProcess.start()` setting status to `"running"`
and the `_watch_exit` daemon thread immediately calling `proc.wait()` on a
mock that returns instantly. Any new tests involving `ServerProcess.start()`
should follow the same pattern.

---

## `.env` field reference

All fields written by the wizard:

| Env var | Wizard field | Default | Required |
|---------|-------------|---------|----------|
| `OBSIDIAN_MCP_VAULT_PATH` | Vault Path | — | ✅ |
| `OBSIDIAN_MCP_SERVER_NAME` | Server Name | `obsidian-mcp` | |
| `OBSIDIAN_MCP_LOG_LEVEL` | Log Level | `INFO` | |
| `OBSIDIAN_MCP_PERMISSION_PROFILE` | Permission Profile | `safe_write` | |
| `OBSIDIAN_MCP_ADAPTER_MODE` | Adapter Mode | `auto` | |
| `OBSIDIAN_MCP_ADAPTER_HOST` | Adapter Host | `127.0.0.1` | |
| `OBSIDIAN_MCP_ADAPTER_PORT` | Adapter Port | `27123` | |
| `OBSIDIAN_MCP_ADAPTER_API_KEY` | API Key | — | Only for REST/auto mode |
| `OBSIDIAN_MCP_TEMPLATES_FOLDER` | Templates Folder | `Templates` | |
| `OBSIDIAN_MCP_WEB_HOST` | Web Host | `127.0.0.1` | Only if web UI enabled |
| `OBSIDIAN_MCP_WEB_PORT` | Web Port | `8765` | Only if web UI enabled |

---

## Dependencies introduced

| Package | Used by | Why |
|---------|---------|-----|
| `customtkinter` | Both scripts | Modern dark-themed GUI framework |
| `pystray` | `server_launcher.py` | Cross-platform system tray icon |
| `Pillow` | `server_launcher.py` | Programmatic tray icon rendering |

All three are auto-installed by `_bootstrap_deps()` at script startup if
missing. They are **not** added to `pyproject.toml` because they are optional
GUI tooling — the MCP server itself has no GUI dependency.

If you want to add them as optional extras for pip-based installs:

```toml
[project.optional-dependencies]
gui = ["customtkinter>=5.2.0", "pystray>=0.19.5", "Pillow>=10.0.0"]
```

Then install with `pip install -e ".[gui]"`.
