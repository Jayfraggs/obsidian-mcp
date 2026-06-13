"""MCP server factory for the Obsidian MCP server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import FastMCP

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.logging import get_logger
from obsidian_mcp.vault.service import VaultService

ToolRegistrar = Callable[..., None]
logger = get_logger("server")


def create_server(
    settings: ObsidianMCPSettings,
    tool_registrars: tuple[ToolRegistrar, ...] = (),
    vault_service: VaultService | None = None,
    system_prompt: str | None = None,
) -> FastMCP:
    """Create and configure the MCP server instance.

    Parameters
    ----------
    settings:
        Validated application settings.
    tool_registrars:
        Callables that register tool groups on the server.
    vault_service:
        Pre-built VaultService (adapter already wired). When None a
        default filesystem-backed service is created.
    system_prompt:
        Optional instructions injected as the server-level system prompt.
        Used to carry vault rules into every LLM session.
    """
    # FastMCP accepts instructions= as the server-level system prompt
    server = FastMCP(
        settings.server_name,
        instructions=system_prompt or _default_instructions(),
    )
    for registrar in tool_registrars:
        registrar(server, settings, vault_service=vault_service)
    logger.debug("Created MCP server '%s'.", settings.server_name)
    return server


def _default_instructions() -> str:
    return (
        "You are an Obsidian vault assistant. Use the available tools to read, "
        "create, and update notes. Always prefer atomic notes (one idea per file), "
        "use [[wikilinks]] for internal references, and add proper YAML frontmatter "
        "to every note you create."
    )
