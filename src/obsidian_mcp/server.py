"""MCP server factory for the Obsidian MCP server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import base64
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.server import Icon

from obsidian_mcp.config import ObsidianMCPSettings

# Load and encode the bundled icon once at import time.
# Stored as a 96×96 PNG alongside this module.
def _load_icon() -> Icon | None:
    icon_path = Path(__file__).parent / "icon.png"
    try:
        data = icon_path.read_bytes()
        b64 = base64.b64encode(data).decode()
        return Icon(
            src=f"data:image/png;base64,{b64}",
            mimeType="image/png",
            sizes=["96x96"],
        )
    except Exception:
        return None

_ICON = _load_icon()
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
        icons=[_ICON] if _ICON is not None else None,
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
def _default_instructions() -> str:
    return (
        "You are an expert Obsidian knowledge-management assistant. Think in terms "
        "of interconnected notes rather than documents. Before creating a note, "
        "search for existing content to avoid duplicates. Read notes before editing "
        "them. Prefer atomic notes (one idea per file), use [[wikilinks]] for "
        "connections, and add YAML frontmatter (title, tags, aliases, created, "
        "updated) to new permanent notes. Use str_replace_note for precise edits "
        "instead of replacing entire files. Organize information into reusable, "
        "well-linked knowledge rather than conversation-specific text. Use "
        "Dataview-friendly metadata, Tasks syntax for actionable items, Kanban for "
        "project planning, and generate Excalidraw diagrams when explaining systems, "
        "architectures, workflows, or relationships. Preserve the vault's existing "
        "organization and respond with a concise summary of changes after completing "
        "the requested operations."
    )