#!/usr/bin/env bash
# ════════════════════════════════════════════════════════════════════
#  Obsidian MCP — macOS / Linux installer
#  Run from the obsidian-mcp project folder:
#      chmod +x install.sh && ./install.sh
# ════════════════════════════════════════════════════════════════════

set -e
cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
step() { echo -e "\n${CYAN}[$1]${NC} $2"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; exit 1; }

echo -e "${GREEN}Obsidian MCP — installer${NC}"
echo "Project: $PROJECT_DIR"

# ── Step 1: uv ────────────────────────────────────────────────────────
step 1 "Checking uv..."
if ! command -v uv &>/dev/null; then
    warn "uv not found — installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    command -v uv &>/dev/null || fail "uv install failed. Visit https://docs.astral.sh/uv/"
fi
ok "uv $(uv --version | cut -d' ' -f2)"

# ── Step 2: install ───────────────────────────────────────────────────
step 2 "Installing package..."
uv venv --quiet 2>/dev/null || true
uv pip install -e . --quiet
ok "Package installed"

# ── Step 3: verify scripts ────────────────────────────────────────────
step 3 "Verifying scripts..."
PY_EXE="$PROJECT_DIR/.venv/bin/python"
MCP_EXE="$PROJECT_DIR/.venv/bin/obsidian-mcp"
WEB_EXE="$PROJECT_DIR/.venv/bin/obsidian-mcp-web"
[ -f "$PY_EXE" ]  || fail "python not found in .venv"
[ -f "$MCP_EXE" ] || fail "obsidian-mcp not found in .venv"
[ -f "$WEB_EXE" ] || fail "obsidian-mcp-web not found in .venv"
ok "obsidian-mcp"
ok "obsidian-mcp-web"

# ── Step 4: vault path ────────────────────────────────────────────────
step 4 "Vault path..."
if [ -z "$1" ]; then
    read -rp "  Enter your Obsidian vault path: " VAULT_PATH
else
    VAULT_PATH="$1"
fi
VAULT_PATH="${VAULT_PATH/#\~/$HOME}"   # expand ~
if [ ! -d "$VAULT_PATH" ]; then
    warn "Directory does not exist: $VAULT_PATH"
    warn "Fix OBSIDIAN_MCP_VAULT_PATH in .env before starting"
else
    ok "Vault: $VAULT_PATH"
fi

# ── Step 5: .env ──────────────────────────────────────────────────────
step 5 "Creating .env..."
if [ ! -f ".env" ]; then
cat > .env << ENVEOF
OBSIDIAN_MCP_VAULT_PATH=$VAULT_PATH
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
ENVEOF
    ok ".env created"
else
    ok ".env already exists (not overwritten)"
fi

# ── Step 6: test ──────────────────────────────────────────────────────
step 6 "Testing config..."
OBSIDIAN_MCP_VAULT_PATH="$VAULT_PATH" "$PY_EXE" -m obsidian_mcp check \
    && ok "Config check passed" \
    || warn "Config check failed — review output above"

# ── Step 7: claude_desktop_config.json block ──────────────────────────
step 7 "Claude Desktop config..."
OS="$(uname)"
if [ "$OS" = "Darwin" ]; then
    CONFIG_PATH="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
else
    CONFIG_PATH="$HOME/.config/Claude/claude_desktop_config.json"
fi

cat << CFGEOF

Add this to: $CONFIG_PATH

{
  "mcpServers": {
    "obsidian": {
      "command": "$PY_EXE",
      "args": ["-m", "obsidian_mcp"],
      "env": {
        "OBSIDIAN_MCP_VAULT_PATH": "$VAULT_PATH"
      }
    }
  }
}

CFGEOF

# Save to file
cat > claude_desktop_config_block.txt << CFGEOF
{
  "mcpServers": {
    "obsidian": {
      "command": "$PY_EXE",
      "args": ["-m", "obsidian_mcp"],
      "env": {
        "OBSIDIAN_MCP_VAULT_PATH": "$VAULT_PATH"
      }
    }
  }
}
CFGEOF
ok "Config saved to claude_desktop_config_block.txt"

# ── Done ──────────────────────────────────────────────────────────────
echo -e "\n${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  Installation complete!${NC}"
echo -e "  1. Add the config block above to claude_desktop_config.json"
echo -e "  2. Restart Claude Desktop fully"
echo -e "  3. Look for the 🔌 tools icon in the chat input bar"
echo -e "\n  Web UI: $WEB_EXE"
echo -e "${GREEN}════════════════════════════════════════${NC}\n"
