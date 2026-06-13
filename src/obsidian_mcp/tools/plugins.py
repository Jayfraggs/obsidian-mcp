"""Plugin MCP tool registration.

Registers all plugin-aware tools (Dataview, Tasks, Templater, Excalidraw,
Omnisearch) with the MCP server.  Follows the same pattern as
``tools/core.py`` and ``tools/knowledge.py`` — accepts an optional
pre-built ``VaultService`` so the adapter is wired from ``__main__``.
"""

from __future__ import annotations

from typing import Any, Protocol

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.plugins import (
    DataviewService,
    ExcalidrawService,
    OmnisearchService,
    TasksService,
    TemplaterService,
)
from obsidian_mcp.vault.service import VaultService

PLUGIN_TOOL_NAMES = (
    # Dataview
    "dataview_extract_fields",
    "dataview_add_inline_fields",
    "dataview_build_dashboard",
    "dataview_table_query",
    "dataview_task_query",
    "dataview_list_query",
    # Tasks
    "tasks_list",
    "tasks_aggregate",
    "tasks_create",
    "tasks_complete",
    "tasks_create_note",
    # Templater
    "templater_list_templates",
    "templater_read_template",
    "templater_apply",
    "templater_create_template",
    # Excalidraw
    "excalidraw_generate_architecture",
    "excalidraw_generate_concept_map",
    "excalidraw_parse_elements",
    "excalidraw_add_annotation",
    # Omnisearch
    "omnisearch_suggest_aliases",
    "omnisearch_add_aliases",
    "omnisearch_suggest_keywords",
    "omnisearch_find_poorly_indexed",
    "omnisearch_optimise_note",
    "omnisearch_bulk_optimise",
)


class ToolServer(Protocol):
    def tool(self, name: str): ...  # noqa: E704


def register_plugin_tools(
    server: ToolServer,
    settings: ObsidianMCPSettings,
    vault_service: VaultService | None = None,
) -> None:
    """Register all plugin-aware tools with the MCP server."""
    vault = vault_service or VaultService(settings.vault_path)
    templates_folder = getattr(settings, "templates_folder", "Templates")

    dv  = DataviewService(vault)
    ts  = TasksService(vault)
    tpl = TemplaterService(vault, templates_folder=templates_folder)
    ex  = ExcalidrawService(vault)
    om  = OmnisearchService(vault)

    # ── Dataview ──────────────────────────────────────────────────────

    @server.tool("dataview_extract_fields")
    def dataview_extract_fields(path: str) -> dict[str, Any]:
        """Extract all Dataview-visible fields (frontmatter + inline) from a note.

        Returns merged dict of frontmatter_fields, inline_fields, and a
        combined merged dict the AI can use when building queries.
        """
        return dv.extract_fields(path)

    @server.tool("dataview_add_inline_fields")
    def dataview_add_inline_fields(path: str, fields: dict[str, str]) -> dict[str, Any]:
        """Add or update Dataview inline fields (key:: value) in a note.

        Existing fields with the same key are updated in-place.
        New fields are inserted after the frontmatter block.

        Args:
            path: Vault-relative note path.
            fields: Dict of {field_name: value} to write.
        """
        return dv.add_inline_fields(path, fields)

    @server.tool("dataview_build_dashboard")
    def dataview_build_dashboard(
        path: str,
        title: str,
        folders: list[str] | None = None,
        tags: list[str] | None = None,
        include_tasks: bool = True,
        include_recent: bool = True,
        include_stats: bool = True,
    ) -> dict[str, Any]:
        """Create a comprehensive Dataview dashboard note.

        Generates TABLE, TASK, and LIST query blocks scoped to the
        specified folders and tags.

        Args:
            path: Where to create the dashboard note.
            title: Dashboard heading.
            folders: Vault-relative folders to scope queries to (empty = entire vault).
            tags: Tag filters (without #) for tagged-note sections.
            include_tasks: Add open-tasks TASK query block.
            include_recent: Add recently-updated TABLE query.
            include_stats: Add vault stats section.
        """
        return dv.build_dashboard(
            path, title,
            folders=folders, tags=tags,
            include_tasks=include_tasks,
            include_recent=include_recent,
            include_stats=include_stats,
        )

    @server.tool("dataview_table_query")
    def dataview_table_query(
        fields: list[str],
        from_folder: str = "",
        where: str | None = None,
        sort: str | None = None,
        limit: int | None = None,
    ) -> str:
        """Build a TABLE Dataview query block string.

        Returns the raw markdown query block — paste into any note.

        Args:
            fields: Field names to include as columns (e.g. ["status", "priority", "file.mtime"]).
            from_folder: Vault-relative folder to query from (empty = entire vault).
            where: WHERE clause expression (e.g. 'status != "done"').
            sort: SORT clause (e.g. "priority DESC").
            limit: LIMIT number.
        """
        return dv.table_query(fields, from_folder=from_folder, where=where, sort=sort, limit=limit)

    @server.tool("dataview_task_query")
    def dataview_task_query(
        from_folder: str = "",
        where: str = "!completed",
        group_by: str | None = None,
    ) -> str:
        """Build a TASK Dataview query block string.

        Args:
            from_folder: Vault-relative folder to query (empty = entire vault).
            where: WHERE clause (default: "!completed").
            group_by: GROUP BY expression (e.g. "file.folder").
        """
        return dv.task_query(from_folder=from_folder, where=where, group_by=group_by)

    @server.tool("dataview_list_query")
    def dataview_list_query(
        field: str | None = None,
        from_folder: str = "",
        where: str | None = None,
        sort: str | None = None,
    ) -> str:
        """Build a LIST Dataview query block string."""
        return dv.list_query(field, from_folder=from_folder, where=where, sort=sort)

    # ── Tasks ─────────────────────────────────────────────────────────

    @server.tool("tasks_list")
    def tasks_list(note_path: str, state: str | None = None) -> list[dict[str, Any]]:
        """Parse and return all tasks in a specific note.

        Args:
            note_path: Vault-relative path to the note.
            state: Filter by "open", "done", "cancelled", "in_progress", or None for all.
        """
        return ts.list_tasks(note_path, state=state)

    @server.tool("tasks_aggregate")
    def tasks_aggregate(
        state: str | None = "open",
        folder: str | None = None,
        due_before: str | None = None,
        priority: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Collect and filter tasks across the entire vault (or a folder).

        Args:
            state: "open" | "done" | "cancelled" | "in_progress" | None for all.
            folder: Restrict to notes in this vault-relative folder.
            due_before: ISO date — return tasks due on or before this date.
            priority: "highest" | "high" | "low" | "lowest" | None for all.
            limit: Maximum number of tasks to return (default 50).
        """
        return ts.aggregate_tasks(
            state=state, folder=folder,
            due_before=due_before, priority=priority, limit=limit,
        )

    @server.tool("tasks_create")
    def tasks_create(
        note_path: str,
        text: str,
        due: str | None = None,
        scheduled: str | None = None,
        priority: str | None = None,
        recurrence: str | None = None,
        section: str | None = None,
    ) -> dict[str, Any]:
        """Append a Tasks-plugin formatted task to an existing note.

        Generates correct emoji syntax automatically.

        Args:
            note_path: Vault-relative path to the note.
            text: Task description.
            due: Due date ISO string (YYYY-MM-DD).
            scheduled: Scheduled date ISO string.
            priority: "highest" | "high" | "low" | "lowest".
            recurrence: Recurrence string e.g. "every week", "every month".
            section: Heading to insert task under (created if absent).
        """
        return ts.create_task(
            note_path, text,
            due=due, scheduled=scheduled,
            priority=priority, recurrence=recurrence, section=section,
        )

    @server.tool("tasks_complete")
    def tasks_complete(note_path: str, task_text_fragment: str) -> dict[str, Any]:
        """Mark the first matching open task in a note as done.

        Matches by substring of the task description. Appends ✅ and today's date.

        Args:
            note_path: Vault-relative path to the note.
            task_text_fragment: Substring of the task text to match.
        """
        return ts.complete_task(note_path, task_text_fragment)

    @server.tool("tasks_create_note")
    def tasks_create_note(
        path: str,
        title: str,
        tasks: list[dict[str, Any]],
        tags: list[str] | None = None,
        area: str | None = None,
    ) -> dict[str, Any]:
        """Create a dedicated task note with formatted tasks and a Dataview overview block.

        Args:
            path: Vault-relative output path.
            title: Note title.
            tasks: List of task dicts with keys: text (required), due, scheduled,
                   priority, recurrence (all optional).
            tags: Frontmatter tags.
            area: Area/context label (written as frontmatter field).
        """
        return ts.create_task_note(path, title, tasks, tags=tags, area=area)

    # ── Templater ─────────────────────────────────────────────────────

    @server.tool("templater_list_templates")
    def templater_list_templates() -> list[dict[str, str]]:
        """List all template notes in the configured templates folder.

        Returns [{path, name}] sorted by name.
        """
        return tpl.list_templates()

    @server.tool("templater_read_template")
    def templater_read_template(name_or_path: str) -> dict[str, Any]:
        """Read the raw content of a template (unrendered).

        Args:
            name_or_path: Template name (e.g. "concept") or full vault path.
        """
        return tpl.read_template(name_or_path)

    @server.tool("templater_apply")
    def templater_apply(
        template_name: str,
        output_path: str,
        variables: dict[str, str] | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Render a template and save it as a new note.

        Static tp.* expressions (tp.date.now, tp.file.title) are resolved
        at generation time.  Dynamic <%* %> blocks are preserved for
        Templater to process when the note is opened in Obsidian.

        Args:
            template_name: Template name or path.
            output_path: Vault-relative destination (creates note).
            variables: Custom substitution map {key: value}.
            title: Resolves tp.file.title in the template.
        """
        return tpl.apply_template(template_name, output_path, variables=variables, title=title)

    @server.tool("templater_create_template")
    def templater_create_template(
        name: str,
        template_type: str,
        custom_fields: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a best-practice Templater template scaffold note.

        Args:
            name: Template name (file stem).
            template_type: "concept" | "project" | "journal" | "meeting" | "reference" | "system".
            custom_fields: Additional frontmatter field names to include.
            tags: Tags baked into the template frontmatter.
        """
        return tpl.create_template(name, template_type, custom_fields=custom_fields, tags=tags)

    # ── Excalidraw ────────────────────────────────────────────────────

    @server.tool("excalidraw_generate_architecture")
    def excalidraw_generate_architecture(
        path: str,
        title: str,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, str]],
        layout: str = "layered",
    ) -> dict[str, Any]:
        """Generate an Excalidraw architecture diagram from a node/edge specification.

        Creates a .excalidraw.md file that Obsidian's Excalidraw plugin can open.

        Args:
            path: Output vault path (will append .excalidraw.md if needed).
            title: Diagram title.
            nodes: List of {id, label, type} where type is one of:
                   service | database | queue | external | user
            edges: List of {from, to, label?} connecting node IDs.
            layout: "layered" (L→R) | "grid" | "radial".
        """
        return ex.generate_architecture(path, title, nodes, edges, layout=layout)

    @server.tool("excalidraw_generate_concept_map")
    def excalidraw_generate_concept_map(
        path: str,
        central_concept: str,
        branches: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate a radial concept map centred on one idea.

        Args:
            path: Output vault path.
            central_concept: The central node label.
            branches: List of {label, children: [str]} — second and third level nodes.
        """
        return ex.generate_concept_map(path, central_concept, branches)

    @server.tool("excalidraw_parse_elements")
    def excalidraw_parse_elements(path: str) -> dict[str, Any]:
        """Parse and return the element list from an existing Excalidraw note.

        Returns {path, element_count, elements[]}.
        """
        return ex.parse_elements(path)

    @server.tool("excalidraw_add_annotation")
    def excalidraw_add_annotation(
        path: str,
        text: str,
        x: float = 40.0,
        y: float = 40.0,
    ) -> dict[str, Any]:
        """Add a floating text annotation to an existing Excalidraw diagram.

        Args:
            path: Vault path to the .excalidraw.md note.
            text: Annotation text.
            x: X coordinate (canvas pixels from top-left).
            y: Y coordinate.
        """
        return ex.add_text_annotation(path, text, x=x, y=y)

    # ── Omnisearch ────────────────────────────────────────────────────

    @server.tool("omnisearch_suggest_aliases")
    def omnisearch_suggest_aliases(path: str, limit: int = 5) -> dict[str, Any]:
        """Suggest additional frontmatter aliases for a note.

        Analyses title variations, noun phrases, and wikilink labels from
        other notes that point to this one.

        Returns {existing_aliases, suggested_aliases}.
        """
        return om.suggest_aliases(path, limit)

    @server.tool("omnisearch_add_aliases")
    def omnisearch_add_aliases(path: str, aliases: list[str]) -> dict[str, Any]:
        """Merge new aliases into a note's frontmatter aliases list.

        Returns {added, aliases} — the full merged alias list.
        """
        return om.add_aliases(path, aliases)

    @server.tool("omnisearch_suggest_keywords")
    def omnisearch_suggest_keywords(path: str, limit: int = 8) -> dict[str, Any]:
        """Suggest high-value search keywords missing from the note's title/tags/aliases.

        Returns {suggested_keywords: [{keyword, frequency}]}.
        """
        return om.suggest_keywords(path, limit)

    @server.tool("omnisearch_find_poorly_indexed")
    def omnisearch_find_poorly_indexed(limit: int = 20) -> list[dict[str, Any]]:
        """Audit the vault and return notes that are hard to find via search.

        A note is flagged when it has no title, no aliases, no tags, or a
        non-descriptive filename.

        Returns [{path, issues[], score}] sorted by score (most issues first).
        """
        return om.find_poorly_indexed_notes(limit)

    @server.tool("omnisearch_optimise_note")
    def omnisearch_optimise_note(path: str) -> dict[str, Any]:
        """Run full Omnisearch optimisation analysis on a single note.

        Returns {alias_suggestions, keyword_suggestions, tip} without writing anything.
        """
        return om.optimise_note(path)

    @server.tool("omnisearch_bulk_optimise")
    def omnisearch_bulk_optimise(
        folder: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Return optimisation reports for the most under-indexed notes in the vault.

        Args:
            folder: Restrict to a vault-relative folder (optional).
            limit: Number of notes to report on.
        """
        return om.bulk_optimise(folder=folder, limit=limit)
