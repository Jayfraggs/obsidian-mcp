"""Command-line entry point for the Obsidian MCP server."""

from mcp.server.fastmcp import FastMCP

from obsidian_mcp.config import load_settings
from obsidian_mcp.logging import configure_logging
from obsidian_mcp.server import create_server


def build_server() -> FastMCP:
    """Build a configured MCP server instance."""
    settings = load_settings()
    configure_logging(settings.log_level)
    return create_server(settings)


def main() -> None:
    """Run the configured MCP server."""
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
