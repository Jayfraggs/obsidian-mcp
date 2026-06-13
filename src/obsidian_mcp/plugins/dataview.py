"""DataviewService – generate and inspect Dataview-compatible vault content.

Dataview treats two things as queryable data:
  1. YAML frontmatter fields  (``status: active``)
  2. Inline fields             (``priority:: high``)

This service generates both, builds typed query blocks, and can scan a note
to report all fields Dataview would see — without requiring Dataview to be
running (everything is static markdown generation).
"""

from __future__ import annotations

import re
from typing import Any

from obsidian_mcp.vault.service import VaultService

_INLINE_FIELD_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_\- ]*)::[ \t]*(.+)$", re.MULTILINE)
_TASK_RE = re.compile(
    r"^[ \t]*[-*][ \t]+\[(?P<state>[ xX\-/])\][ \t]+(?P<text>.+?)(?:[ \t]+📅[ \t]*(?P<due>\d{4}-\d{2}-\d{2}))?(?:[ \t]+(?P<pri>[🔼🔽⏫]))?$",
    re.MULTILINE,
)

_PRIORITY_EMOJI = {"🔼": "high", "⏫": "highest", "🔽": "low"}
_STATE_MAP = {" ": "open", "x": "done", "X": "done", "-": "cancelled", "/": "in-progress"}


class DataviewService:
    """Static Dataview markdown generation and field inspection."""

    def __init__(self, vault: VaultService) -> None:
        self._vault = vault

    # ------------------------------------------------------------------ #
    # Field inspection
    # ------------------------------------------------------------------ #

    def extract_fields(self, path: str) -> dict[str, Any]:
        """Return all Dataview-visible fields from a note.

        Merges YAML frontmatter and inline ``key:: value`` fields.
        Inline fields win on collision (they are more intentional).
        """
        note = self._vault.read_note(path)
        metadata = note["metadata"]
        frontmatter_fields: dict[str, Any] = {
            k: v
            for k, v in metadata.items()
            if k not in ("path", "wikilinks", "markdown_links", "task_count",
                         "has_templater", "is_excalidraw")
        }
        inline_fields: dict[str, str] = {}
        for match in _INLINE_FIELD_RE.finditer(note["content"]):
            key = match.group(1).strip()
            inline_fields[key] = match.group(2).strip()

        return {
            "path": note["path"],
            "frontmatter_fields": frontmatter_fields,
            "inline_fields": inline_fields,
            "merged": {**frontmatter_fields, **inline_fields},
        }

    # ------------------------------------------------------------------ #
    # Property injection
    # ------------------------------------------------------------------ #

    def add_inline_fields(self, path: str, fields: dict[str, str]) -> dict[str, Any]:
        """Append ``key:: value`` inline fields to a note.

        Fields are appended before the first heading (or at the top if none).
        Existing fields with the same key are updated in-place.
        """
        note = self._vault.read_note(path)
        content = note["content"]

        # Update existing inline fields
        for key, value in fields.items():
            pattern = re.compile(rf"^{re.escape(key)}::[ \t]*.+$", re.MULTILINE)
            replacement = f"{key}:: {value}"
            if pattern.search(content):
                content = pattern.sub(replacement, content, count=1)
            else:
                # Insert after frontmatter block or at top
                fm_end = _frontmatter_end(content)
                new_line = f"{key}:: {value}\n"
                content = content[:fm_end] + new_line + content[fm_end:]

        return self._vault.update_note(path, content)

    # ------------------------------------------------------------------ #
    # Dashboard generation
    # ------------------------------------------------------------------ #

    def build_dashboard(
        self,
        path: str,
        title: str,
        *,
        folders: list[str] | None = None,
        tags: list[str] | None = None,
        include_tasks: bool = True,
        include_recent: bool = True,
        include_stats: bool = True,
    ) -> dict[str, Any]:
        """Generate a comprehensive Dataview dashboard note.

        Parameters
        ----------
        folders:
            Vault-relative folder paths to scope queries to.
            Defaults to the entire vault (``""``) when empty.
        tags:
            Tag filters (without ``#``) applied to tagged-note sections.
        include_tasks:
            Add an open-tasks TASK query block.
        include_recent:
            Add a recently-updated TABLE query.
        include_stats:
            Add a vault-stats section with note/task counts.
        """
        scopes = folders or [""]
        tag_list = tags or []
        sections: list[str] = [f"# {title}", ""]

        if include_stats:
            sections += self._stats_section()

        if include_recent:
            sections += self._recent_section(scopes)

        if include_tasks:
            sections += self._tasks_section(scopes)

        if tag_list:
            sections += self._tags_section(tag_list)

        content = "\n".join(sections) + "\n"
        return self._vault.create_note(path, content)

    # ------------------------------------------------------------------ #
    # Query builders (return markdown strings)
    # ------------------------------------------------------------------ #

    def table_query(
        self,
        fields: list[str],
        *,
        from_folder: str = "",
        where: str | None = None,
        sort: str | None = None,
        limit: int | None = None,
    ) -> str:
        """Build a TABLE Dataview query block."""
        lines = ["```dataview", f"TABLE {', '.join(fields)}"]
        if from_folder:
            lines.append(f'FROM "{from_folder}"')
        if where:
            lines.append(f"WHERE {where}")
        if sort:
            lines.append(f"SORT {sort}")
        if limit:
            lines.append(f"LIMIT {limit}")
        lines.append("```")
        return "\n".join(lines)

    def task_query(
        self,
        *,
        from_folder: str = "",
        where: str = "!completed",
        group_by: str | None = None,
    ) -> str:
        """Build a TASK Dataview query block."""
        lines = ["```dataview", "TASK"]
        if from_folder:
            lines.append(f'FROM "{from_folder}"')
        if where:
            lines.append(f"WHERE {where}")
        if group_by:
            lines.append(f"GROUP BY {group_by}")
        lines.append("```")
        return "\n".join(lines)

    def list_query(
        self,
        field: str | None = None,
        *,
        from_folder: str = "",
        where: str | None = None,
        sort: str | None = None,
    ) -> str:
        """Build a LIST Dataview query block."""
        header = f"LIST {field}" if field else "LIST"
        lines = ["```dataview", header]
        if from_folder:
            lines.append(f'FROM "{from_folder}"')
        if where:
            lines.append(f"WHERE {where}")
        if sort:
            lines.append(f"SORT {sort}")
        lines.append("```")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _stats_section(self) -> list[str]:
        all_files = [f for f in self._vault.list_files() if f.endswith(".md")]
        total_notes = len(all_files)
        total_tasks = sum(
            self._vault.read_note(f)["metadata"].get("task_count", 0)
            for f in all_files
        )
        return [
            "## Vault stats",
            "",
            f"- **Notes:** {total_notes}",
            f"- **Open tasks (approx):** {total_tasks}",
            "",
        ]

    def _recent_section(self, scopes: list[str]) -> list[str]:
        from_clause = " OR ".join(f'"{s}"' for s in scopes if s) or '""'
        return [
            "## Recently updated",
            "",
            "```dataview",
            "TABLE file.mtime AS Updated, status",
            f"FROM {from_clause}",
            "SORT file.mtime DESC",
            "LIMIT 15",
            "```",
            "",
        ]

    def _tasks_section(self, scopes: list[str]) -> list[str]:
        from_clause = " OR ".join(f'"{s}"' for s in scopes if s) or '""'
        return [
            "## Open tasks",
            "",
            "```dataview",
            "TASK",
            f"FROM {from_clause}",
            "WHERE !completed",
            "SORT due ASC",
            "```",
            "",
        ]

    def _tags_section(self, tags: list[str]) -> list[str]:
        lines: list[str] = ["## By tag", ""]
        for tag in tags:
            lines += [
                f"### #{tag}",
                "",
                "```dataview",
                "LIST",
                f'FROM #{tag}',
                "SORT file.name ASC",
                "```",
                "",
            ]
        return lines


def _frontmatter_end(content: str) -> int:
    """Return the character index just after the closing ``---`` fence."""
    if not content.startswith("---"):
        return 0
    end = content.find("\n---", 3)
    return end + 4 if end != -1 else 0
