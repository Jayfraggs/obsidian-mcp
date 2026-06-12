"""MCP server factory for the Obsidian MCP server."""

from collections.abc import Callable

from mcp.server.fastmcp import FastMCP

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.logging import get_logger

ToolRegistrar = Callable[[FastMCP, ObsidianMCPSettings], None]

logger = get_logger("server")


def create_server(
    settings: ObsidianMCPSettings,
    tool_registrars: tuple[ToolRegistrar, ...] = (),
) -> FastMCP:
    """Create and configure the MCP server instance."""
    server = FastMCP(settings.server_name)
    _register_tools(server, settings, tool_registrars)
    logger.debug("Created MCP server '%s'.", settings.server_name)
    return server


def _register_tools(
    server: FastMCP,
    settings: ObsidianMCPSettings,
    tool_registrars: tuple[ToolRegistrar, ...],
) -> None:
    """Register tool groups with the MCP server."""
    for registrar in tool_registrars:
        registrar(server, settings)
