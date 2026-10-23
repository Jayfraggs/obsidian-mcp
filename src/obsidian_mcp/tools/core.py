"""Core MCP tool registration for Obsidian vault operations."""

from typing import Any, Protocol

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
        whole_word: bool = False,
        case_sensitive: bool = True,
        dry_run: bool = True,
        backup: bool = False,
        exception_rules: list[dict[str, Any]] | None = None,
    ):
        """Replace old_str with new_str across every matching note in the vault.

        ALWAYS runs as dry_run=True by default — set dry_run=False only after
        reviewing the preview output. No files are written during a dry run.

        Parameters
        ----------
        old_str:
            The exact string to find and replace.
        new_str:
            The replacement string. Pass "" to delete old_str.
        require_unique_per_note:
            Default True — skip notes where old_str appears more than once,
            reporting them under "ambiguous". Set False to replace ALL
            occurrences in every matched note.
        path_glob:
            Limit scope to notes whose vault-relative path contains this
            substring. E.g. "Projects/" scopes to the Projects folder only.
        whole_word:
            Default False. When True, only match old_str when it is not
            immediately preceded or followed by a letter or digit.
            Correct for hyphenated model names like "DeepSeek-V4-Flash"
            (standard \\b word boundaries break at hyphens and are NOT used).
        case_sensitive:
            Default True. Set False for case-insensitive matching.
        dry_run:
            Default True. When True, returns a full preview of what would
            change without touching any files. Set False to commit changes.
        backup:
            Default False. When True (and dry_run=False), copies each
            affected note to .mcp-backups/<timestamp>/ inside the vault
            before overwriting. Ignored during dry runs.
        exception_rules:
            List of rule dicts. A note matching ANY rule is skipped entirely.
            Each dict must have "type" and "value" keys.

            Rule types:
              "folder"          — skip notes inside this folder name
                                  {"type": "folder", "value": "30-References"}
              "tag"             — skip notes with this Obsidian tag
                                  {"type": "tag", "value": "#archived"}
              "frontmatter"     — skip notes whose YAML frontmatter contains
                                  this key:value substring
                                  {"type": "frontmatter", "value": "status: locked"}
              "path_glob"       — skip notes whose path contains this substring
                                  {"type": "path_glob", "value": "Templates"}
              "contains_string" — skip notes containing this sentinel string
                                  {"type": "contains_string", "value": "DO NOT EDIT"}

        Returns
        -------
        {
          "dry_run": bool,
          "updated": [list of paths changed / would change],
          "skipped": [{"path": ..., "reason": ...}, ...],
          "ambiguous": [list of paths skipped due to multiple occurrences],
          "unchanged_count": int,
          "backup_dir": str or null
        }

        Recommended workflow:
          1. str_replace_vault(old_str=..., new_str=..., dry_run=True)
          2. Review "updated", "skipped", "ambiguous" in the result.
          3. If satisfied: str_replace_vault(..., dry_run=False, backup=True)
        """
        return service.str_replace_vault(
            old_str,
            new_str,
            require_unique_per_note=require_unique_per_note,
            path_glob=path_glob,
            whole_word=whole_word,
            case_sensitive=case_sensitive,
            dry_run=dry_run,
            backup=backup,
            exception_rules=exception_rules,
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
