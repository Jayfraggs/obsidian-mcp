# Obsidian MCP — Setup Wizard & Server Launcher

## Files

| File | Purpose | Where it goes |
|---|---|---|
| `setup_wizard.py` | GUI setup wizard | Repo root |
| `server_launcher.py` | Tray icon + status panel | Repo root |
| `test_setup_wizard.py` | Test suite | `_test_/unit/test_setup_wizard.py` |

## How to run

**First-time setup:**
```bash
python setup_wizard.py
```

**Daily use (after setup):**
```bash
python server_launcher.py
```
Or use the desktop shortcut created by the wizard.

## Dependencies
All installed automatically on first run:
- `customtkinter` — GUI
- `pystray` — system tray icon
- `Pillow` — tray icon rendering

## Tests
```bash
pytest _test_/unit/test_setup_wizard.py -v
```
Expected: 31 passed.

## Wizard flow
1. Welcome — Python + uv check
2. Prerequisites — required/suggested plugins with acknowledgement
3. REST API Setup — step-by-step guide for Local REST API plugin
4. Configure — all .env fields with live adapter field toggling
5. Review — .env preview before writing
6. Install — uv install, .env write, Claude Desktop merge, shortcut creation
7. Done — copy server command, launch server button

## Server Launcher features
- Auto-starts server on launch
- System tray icon (colour reflects status: purple=running, grey=stopped, red=error)
- Right-click tray menu: Start / Stop / Restart / Open Status Panel / Quit
- Status panel: live log tail, Start/Stop/Restart buttons, "Run Setup Again" button
- Double-click tray icon opens status panel
