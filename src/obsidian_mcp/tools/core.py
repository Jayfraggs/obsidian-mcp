"""Core MCP tool registration for Obsidian vault operations."""

from typing import Protocol

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.vault.service import VaultService

CORE_TOOL_NAMES = (
    "read_note",
    "create_note",
    "update_note",
    "append_note",
    "str_replace_note",
    "str_replace_vault",
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
    def read_note(path: str, include_backlinks: bool = False):
        """Read a markdown note from the vault. include_backlinks=True adds backlink scan (slow on large vaults)."""
        return service.read_note(path, include_backlinks=include_backlinks)

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

    @server.tool("str_replace_note")
    def str_replace_note(path: str, old_str: str, new_str: str = ""):
        """Replace one exact occurrence of old_str with new_str in a single note.

        Use this instead of update_note when changing a small part of a
        note — it avoids resending the entire note content and is safer:
        old_str must match the raw note content exactly and occur exactly
        once, or the call fails with an error rather than guessing.

        If old_str occurs more than once, add more surrounding context
        (e.g. a preceding heading or line) to make it unique before retrying.
        """
        return service.str_replace_note(path, old_str, new_str)

    @server.tool("str_replace_vault")
    def str_replace_vault(
        old_str: str,
        new_str: str = "",
        require_unique_per_note: bool = True,
        path_glob: str | None = None,
    ):
        """Replace old_str with new_str across every matching note in the vault.

        Best-effort batch operation — one note failing to match does not
        abort the rest. Use path_glob (a substring of the vault path, e.g.
        "Projects/") to scope the replacement to a folder.

        By default (require_unique_per_note=True) any note where old_str
        occurs more than once is SKIPPED and listed under "ambiguous" in
        the result, rather than guessing which occurrence to change.
        Set require_unique_per_note=False only when you specifically want
        every occurrence replaced everywhere it appears — e.g. a vault-wide
        rename of a term you've confirmed is unambiguous in context.

        Returns {updated: [...], ambiguous: [...], unchanged_count: N}.
        Review "ambiguous" and consider str_replace_note with extra
        context for those notes individually.
        """
        return service.str_replace_vault(
            old_str, new_str,
            require_unique_per_note=require_unique_per_note,
            path_glob=path_glob,
        )

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
