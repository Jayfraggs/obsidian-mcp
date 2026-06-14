# Windows Fix — "process cannot access the file" error

## Root cause

`uv run obsidian-mcp` rebuilds the package every time Claude Desktop connects.
During rebuild it tries to replace `obsidian-mcp-web.exe` — which a previous
session is still holding open. Windows file locking makes this fatal.

## Fix (do this once, then never needed again)

### Step 1 — Kill any stuck processes

Open PowerShell and run:

```powershell
Stop-Process -Name "obsidian-mcp" -ErrorAction SilentlyContinue
Stop-Process -Name "obsidian-mcp-web" -ErrorAction SilentlyContinue
```

Or open Task Manager → Details tab → end any `obsidian-mcp.exe` or
`obsidian-mcp-web.exe` processes manually.

### Step 2 — Install the package properly (one-time only)

Open PowerShell **in the obsidian-mcp project folder**:

```powershell
cd "C:\Users\Olabode Nathaniel\Code\obsidian-mcp"
uv pip install -e .
```

This installs the scripts permanently into the venv. After this, `uv run`
will never need to rebuild them again — it just uses what's there.

### Step 3 — Update claude_desktop_config.json

Location: `%APPDATA%\Claude\claude_desktop_config.json`

Open it in any text editor and **replace** the current server block.

#### Recommended: Option A — python -m (no .exe locking ever)

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "C:\\Users\\Olabode Nathaniel\\Code\\obsidian-mcp\\.venv\\Scripts\\python.exe",
      "args": ["-m", "obsidian_mcp"],
      "env": {
        "OBSIDIAN_MCP_VAULT_PATH": "C:\\path\\to\\your\\ObsidianVault"
      }
    }
  }
}
```

> Replace `C:\\path\\to\\your\\ObsidianVault` with your actual vault path.
> Use double backslashes in JSON — `C:\\Users\\Olabode Nathaniel\\Vault`.

#### Option B — Call the installed .exe directly

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "C:\\Users\\Olabode Nathaniel\\Code\\obsidian-mcp\\.venv\\Scripts\\obsidian-mcp.exe",
      "args": [],
      "env": {
        "OBSIDIAN_MCP_VAULT_PATH": "C:\\path\\to\\your\\ObsidianVault"
      }
    }
  }
}
```

#### Option C — uv run with --no-sync (prevents rebuild on every connect)

```json
{
  "mcpServers": {
    "obsidian": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\Olabode Nathaniel\\Code\\obsidian-mcp",
        "run",
        "--no-sync",
        "obsidian-mcp"
      ],
      "env": {
        "OBSIDIAN_MCP_VAULT_PATH": "C:\\path\\to\\your\\ObsidianVault"
      }
    }
  }
}
```

### Step 4 — Restart Claude Desktop

Quit fully: right-click the system tray icon → **Quit** (not just close the window).
Then relaunch. You should see the 🔌 tools icon in the chat input bar.

---

## Test it manually first

Before relaunching Claude Desktop, confirm the server starts cleanly:

```powershell
cd "C:\Users\Olabode Nathaniel\Code\obsidian-mcp"
.venv\Scripts\python.exe -m obsidian_mcp
```

It should start silently with no output (it waits for stdio from Claude).
Press **Ctrl+C** to stop. If it errors here, fix it here before trying Claude Desktop.

---

## Still broken? Nuclear option

```powershell
cd "C:\Users\Olabode Nathaniel\Code\obsidian-mcp"
Remove-Item -Recurse -Force .venv
uv venv
uv pip install -e .
.venv\Scripts\python.exe -m obsidian_mcp   # test it
```

Then update config.json and restart Claude Desktop.

---

## Verify your vault path

```powershell
Test-Path "C:\path\to\your\ObsidianVault"
# Must print: True
```

If it prints `False`, the path is wrong — fix `OBSIDIAN_MCP_VAULT_PATH`.
