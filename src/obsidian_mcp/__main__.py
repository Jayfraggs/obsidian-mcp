"""Command-line entry point for the Obsidian MCP server."""

from __future__ import annotations

import uvicorn
from mcp.server.fastmcp import FastMCP

from obsidian_mcp.adapters import AutoAdapter
from obsidian_mcp.config import load_settings
from obsidian_mcp.logging import configure_logging, get_logger
from obsidian_mcp.server import create_server
from obsidian_mcp.tools.core import register_core_tools
from obsidian_mcp.tools.knowledge import register_knowledge_tools
from obsidian_mcp.tools.plugins import register_plugin_tools
from obsidian_mcp.vault.service import VaultService
from obsidian_mcp.web.app import create_web_app, _load_rules, _build_system_prompt

logger = get_logger("main")


def _build_vault_service():
    """Load settings, probe adapters, return (settings, vault_service)."""
    settings = load_settings()
    configure_logging(settings.log_level)

    adapter = AutoAdapter.from_settings(settings)
    logger.info(
        "Vault adapter: %s  |  vault: %s",
        adapter.backend_name,
        settings.vault_path,
    )
    vault_service = VaultService(settings.vault_path, adapter=adapter)
    return settings, vault_service


def build_server() -> FastMCP:
    """Build a fully configured MCP server instance with all tool groups."""
    settings, vault_service = _build_vault_service()

    # Load vault rules and inject as MCP server instructions
    rules = _load_rules()
    system_prompt = _build_system_prompt(rules)
    logger.info("Loaded %d vault rules.", len([l for l in rules.splitlines() if l.strip()]))

    return create_server(
        settings,
        tool_registrars=(
            register_core_tools,
            register_knowledge_tools,
            register_plugin_tools,
        ),
        vault_service=vault_service,
        system_prompt=system_prompt,
    )


def main() -> None:
    """Run the MCP server (stdio transport — for Claude Desktop and compatible clients)."""
    server = build_server()
    server.run()


def web_main() -> None:
    """Run the local Web UI (HTTP)."""
    settings, vault_service = _build_vault_service()
    uvicorn.run(
        create_web_app(settings, vault_service=vault_service),
        host=settings.web_host,
        port=settings.web_port,
    )


if __name__ == "__main__":
    main()
