# ════════════════════════════════════════════════════════════════════
#  Obsidian MCP — Windows installer
#  Run from the obsidian-mcp project folder:
#      cd "C:\path\to\obsidian-mcp"
#      .\install.ps1
# ════════════════════════════════════════════════════════════════════

param(
    [string]$VaultPath = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot

function Write-Step($n, $msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Write-Ok($msg)       { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn($msg)     { Write-Host "  ! $msg" -ForegroundColor Yellow }
function Write-Fail($msg)     { Write-Host "  ✗ $msg" -ForegroundColor Red; exit 1 }

Write-Host "`nObsidian MCP — Windows installer" -ForegroundColor White
Write-Host "Project: $ProjectDir`n"

# ── Step 1: check uv ─────────────────────────────────────────────────
Write-Step 1 "Checking uv..."
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Warn "uv not found. Installing via winget..."
    winget install --id=astral-sh.uv -e --silent
    $env:PATH += ";$env:LOCALAPPDATA\uv\bin"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Fail "uv installation failed. Install manually from https://docs.astral.sh/uv/"
    }
}
$uvVersion = (uv --version) -replace "uv ", ""
Write-Ok "uv $uvVersion"

# ── Step 2: kill any running instances ───────────────────────────────
Write-Step 2 "Stopping any running obsidian-mcp processes..."
@("obsidian-mcp", "obsidian-mcp-web") | ForEach-Object {
    $procs = Get-Process -Name $_ -ErrorAction SilentlyContinue
    if ($procs) {
        $procs | Stop-Process -Force
        Write-Ok "Stopped $_ ($($procs.Count) process(es))"
    }
}
Start-Sleep -Milliseconds 500

# ── Step 3: remove stale venv if --Force ─────────────────────────────
if ($Force -and (Test-Path "$ProjectDir\.venv")) {
    Write-Step 3 "Removing old .venv (--Force)..."
    Remove-Item -Recurse -Force "$ProjectDir\.venv"
    Write-Ok ".venv removed"
} else {
    Write-Step 3 "Checking .venv..."
}

# ── Step 4: create venv and install ──────────────────────────────────
Write-Step 4 "Installing package into venv..."
Set-Location $ProjectDir
uv venv --quiet
uv pip install -e . --quiet
Write-Ok "Package installed"

# ── Step 5: verify scripts exist ─────────────────────────────────────
Write-Step 5 "Verifying installed scripts..."
$mcpExe = "$ProjectDir\.venv\Scripts\obsidian-mcp.exe"
$webExe = "$ProjectDir\.venv\Scripts\obsidian-mcp-web.exe"
$pyExe  = "$ProjectDir\.venv\Scripts\python.exe"

if (-not (Test-Path $mcpExe)) { Write-Fail "obsidian-mcp.exe not found after install" }
if (-not (Test-Path $webExe)) { Write-Fail "obsidian-mcp-web.exe not found after install" }
Write-Ok "obsidian-mcp.exe"
Write-Ok "obsidian-mcp-web.exe"
Write-Ok "python.exe"

# ── Step 6: get vault path ────────────────────────────────────────────
Write-Step 6 "Vault path..."
if (-not $VaultPath) {
    $VaultPath = Read-Host "  Enter your Obsidian vault path (absolute)"
}
$VaultPath = $VaultPath.Trim().Trim('"')
if (-not (Test-Path $VaultPath)) {
    Write-Warn "Path does not exist: $VaultPath"
    Write-Warn "Continuing anyway — fix OBSIDIAN_MCP_VAULT_PATH in .env before starting"
} else {
    Write-Ok "Vault found: $VaultPath"
}

# ── Step 7: create .env ───────────────────────────────────────────────
Write-Step 7 "Creating .env..."
$envFile = "$ProjectDir\.env"
if (-not (Test-Path $envFile)) {
    $envContent = @"
OBSIDIAN_MCP_VAULT_PATH=$VaultPath
OBSIDIAN_MCP_SERVER_NAME=obsidian-mcp
OBSIDIAN_MCP_LOG_LEVEL=INFO
OBSIDIAN_MCP_PERMISSION_PROFILE=safe_write
OBSIDIAN_MCP_ADAPTER_MODE=auto
OBSIDIAN_MCP_ADAPTER_API_KEY=
OBSIDIAN_MCP_ADAPTER_HOST=127.0.0.1
OBSIDIAN_MCP_ADAPTER_PORT=27123
OBSIDIAN_MCP_WEB_HOST=127.0.0.1
OBSIDIAN_MCP_WEB_PORT=8765
OBSIDIAN_MCP_TEMPLATES_FOLDER=Templates
"@
    $envContent | Out-File -FilePath $envFile -Encoding utf8
    Write-Ok ".env created"
} else {
    Write-Ok ".env already exists (not overwritten)"
}

# ── Step 8: test the server ───────────────────────────────────────────
Write-Step 8 "Testing server startup..."
$env:OBSIDIAN_MCP_VAULT_PATH = $VaultPath
$testResult = & $pyExe -m obsidian_mcp check 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Ok "Config check passed"
} else {
    Write-Warn "Config check returned issues:"
    $testResult | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
}

# ── Step 9: generate claude_desktop_config.json block ────────────────
Write-Step 9 "Claude Desktop config..."
$escapedPy  = $pyExe  -replace "\\", "\\\\"
$escapedDir = $ProjectDir -replace "\\", "\\\\"
$configBlock = @"

Add this to %APPDATA%\Claude\claude_desktop_config.json:

{
  "mcpServers": {
    "obsidian": {
      "command": "$escapedPy",
      "args": ["-m", "obsidian_mcp"],
      "env": {
        "OBSIDIAN_MCP_VAULT_PATH": "$($VaultPath -replace "\\", "\\\\")"
      }
    }
  }
}

"@

Write-Host $configBlock -ForegroundColor White

# Save to file for easy copying
$configBlock | Out-File -FilePath "$ProjectDir\claude_desktop_config_block.txt" -Encoding utf8
Write-Ok "Config block saved to: claude_desktop_config_block.txt"

# ── Done ──────────────────────────────────────────────────────────────
Write-Host "`n════════════════════════════════════════" -ForegroundColor Green
Write-Host "  Installation complete!" -ForegroundColor Green
Write-Host "  Next steps:" -ForegroundColor Green
Write-Host "  1. Add the config block above to claude_desktop_config.json" -ForegroundColor White
Write-Host "  2. Restart Claude Desktop (Quit from system tray, then relaunch)" -ForegroundColor White
Write-Host "  3. Look for the tools icon in the Claude chat input bar" -ForegroundColor White
Write-Host "`n  Web UI: run  .venv\Scripts\obsidian-mcp-web.exe" -ForegroundColor White
Write-Host "════════════════════════════════════════`n" -ForegroundColor Green
