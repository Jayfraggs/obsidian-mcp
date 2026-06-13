"""Core MCP tool registration for Obsidian vault operations."""

from typing import Protocol

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.vault.service import VaultService

CORE_TOOL_NAMES = (
    "read_note",
    "create_note",
    "update_note",
    "append_note",
    "delete_note",
    "move_note",
    "rename_note",
    "search_notes",
    "list_files",
    "list_folders",
)


class ToolServer(Protocol):
    """Minimal MCP server protocol needed for tool registration."""

    def tool(self, name: str):  # type: ignore[no-untyped-def]
        """Return a decorator that registers an MCP tool."""


def register_core_tools(
    server: ToolServer,
    settings: ObsidianMCPSettings,
    vault_service: VaultService | None = None,
) -> None:
    """Register core Obsidian vault tools with an MCP server.

    Parameters
    ----------
    vault_service:
        Pre-built service (with adapter wired).  When *None* a default
        filesystem-backed service is created from ``settings.vault_path``.
    """
    service = vault_service or VaultService(settings.vault_path)

    @server.tool("read_note")
    def read_note(path: str):
        """Read a markdown note from the configured Obsidian vault."""
        return service.read_note(path)

    @server.tool("create_note")
    def create_note(path: str, content: str):
        """Create a markdown note in the configured Obsidian vault."""
        return service.create_note(path, content)

    @server.tool("update_note")
    def update_note(path: str, content: str):
        """Replace the full content of a markdown note."""
        return service.update_note(path, content)

    @server.tool("append_note")
    def append_note(path: str, content: str):
        """Append content to a markdown note."""
        return service.append_note(path, content)

    @server.tool("delete_note")
    def delete_note(path: str):
        """Delete a markdown note from the configured Obsidian vault."""
        return service.delete_note(path)

    @server.tool("move_note")
    def move_note(source: str, destination: str):
        """Move a markdown note to another vault-relative path."""
        return service.move_note(source, destination)

    @server.tool("rename_note")
    def rename_note(path: str, new_name: str):
        """Rename a markdown note within its current folder."""
        return service.rename_note(path, new_name)

    @server.tool("search_notes")
    def search_notes(query: str, limit: int = 10):
        """Search markdown notes by text content."""
        return service.search_notes(query, limit)

    @server.tool("list_files")
    def list_files():
        """List files in the configured Obsidian vault."""
        return service.list_files()

    @server.tool("list_folders")
    def list_folders():
        """List folders in the configured Obsidian vault."""
        return service.list_folders()
