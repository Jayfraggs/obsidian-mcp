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
    KanbanService,
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
    "excalidraw_write_script",
    "excalidraw_embed_in_note",
    "excalidraw_install_scripts",
    "excalidraw_list_bundled_scripts",
    # Kanban
    "kanban_create_board",
    "kanban_create_simple_board",
    "kanban_add_card",
    "kanban_move_card",
    "kanban_complete_card",
    "kanban_read_board",
    "kanban_lane_summary",
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
    kb  = KanbanService(vault)

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
        Use excalidraw_embed_in_note afterwards to display the diagram inline in any .md note.

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

        Use excalidraw_embed_in_note afterwards to display it inline in any .md note.

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

    @server.tool("excalidraw_write_script")
    def excalidraw_write_script(
        script_name: str,
        description: str,
        js_code: str,
        scripts_folder: str = "Excalidraw/Scripts",
    ) -> dict[str, Any]:
        """Write a JavaScript automation script for Excalidraw's Script Engine.

        The script is saved as a .md file in the vault's scripts folder and
        immediately appears in Obsidian's command palette as
        "Excalidraw Script: <script_name>" — no restart needed.

        The Script Engine injects two globals into every script:
          - ea  : ExcalidrawAutomate instance bound to the active drawing.
                  Provides addRect(), addText(), addArrow(), connectObjects(),
                  getViewSelectedElements(), addElementsToView(), etc.
          - utils: UI helpers — utils.inputPrompt(), utils.suggester().

        Use this to author automations the user can trigger interactively,
        such as re-colouring nodes, adding boxes around selections, bulk
        relabelling, or custom layout adjustments.

        Args:
            script_name: Name shown in command palette (no .md extension).
            description: Human-readable explanation stored above the code.
            js_code: Valid JavaScript using the ea / utils globals.
            scripts_folder: Vault path matching Excalidraw Settings →
                            Script Engine folder (default "Excalidraw/Scripts").
        """
        return ex.write_ea_script(script_name, description, js_code, scripts_folder=scripts_folder)

    @server.tool("excalidraw_embed_in_note")
    def excalidraw_embed_in_note(
        drawing_path: str,
        note_path: str,
        heading: str | None = None,
        width: int | None = None,
    ) -> dict[str, Any]:
        """Embed an Excalidraw drawing inline in a markdown note.

        Appends a ![[wikilink]] transclusion so the diagram renders
        directly in Obsidian's reading view inside the target note.
        Creates the note if it doesn't exist.

        Use this after excalidraw_generate_architecture or
        excalidraw_generate_concept_map to surface the diagram inside
        a relevant index note, runbook, or MOC.

        Args:
            drawing_path: Vault path of the .excalidraw.md file.
            note_path: Vault path of the markdown note to embed into.
            heading: Optional ## heading to insert before the embed.
            width: Optional pixel width, e.g. 600.
        """
        return ex.embed_in_note(drawing_path, note_path, heading=heading, width=width)

    @server.tool("excalidraw_install_scripts")
    def excalidraw_install_scripts(
        scripts: list[str] | None = None,
        scripts_folder: str = "Excalidraw/Scripts",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Install bundled Excalidraw Script Engine scripts into the vault.

        Scripts appear instantly in Obsidian's command palette as
        "Excalidraw Script: <name>" and can be assigned hotkeys.
        No Obsidian restart required.

        The bundled scripts include:

        Layout & structure:
          - Auto Layout          — ELK-powered automatic layout (layered/radial/tree)
          - Mindmap Builder      — Full interactive mindmap with sidepanel UI
          - Mindmap format       — Auto-format a left-to-right mindmap
          - Mindmap connector    — Connect nodes with mindmap-style right-angle lines
          - Elbow connectors     — Convert arrows to right-angle elbow connectors

        Drawing workflow:
          - Connect elements     — Connect two selected objects with a bound arrow
          - Box Selected Elements       — Wrap selection in a bounding box
          - Box Each Selected Groups    — Box each group individually
          - Add Next Step in Process    — Prompt + create + connect a process step
          - Set Dimensions       — Set exact x/y/width/height on an element
          - Concatenate lines    — Merge two arrows/lines into one

        Conversion & editing:
          - Convert freedraw to line
          - Convert selected text elements to sticky notes
          - Add Connector Point  — Add bullet-point circles to text elements
          - Copy Selected Element Styles to Global

        Vault linking:
          - Add Link to Existing File and Open
          - Add Link to New Page and Open
          - Deconstruct selected elements into new drawing

        Use excalidraw_list_bundled_scripts for the full list with descriptions.

        Args:
            scripts: Names to install (None = all). Get names from
                     excalidraw_list_bundled_scripts.
            scripts_folder: Vault path matching Excalidraw Settings →
                            Script Engine folder. Default "Excalidraw/Scripts".
            overwrite: Replace existing scripts. Default False (skip).
        """
        return ex.install_scripts(scripts=scripts, scripts_folder=scripts_folder, overwrite=overwrite)

    @server.tool("excalidraw_list_bundled_scripts")
    def excalidraw_list_bundled_scripts() -> list[dict[str, str]]:
        """List all Excalidraw scripts bundled with obsidian-mcp.

        Returns [{name, description}] for each script.
        Pass name values to excalidraw_install_scripts(scripts=[...])
        to install a specific subset.
        """
        return ex.list_bundled_scripts()

    # ── Kanban ────────────────────────────────────────────────────────

    @server.tool("kanban_create_board")
    def kanban_create_board(
        path: str,
        title: str,
        lanes: list[dict[str, Any]],
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new Kanban board with lanes and cards in one call.

        Produces a .md file with 'kanban-plugin: basic' frontmatter that
        Obsidian's Kanban plugin renders as a drag-and-drop board.

        Each lane in `lanes` is a dict:
            {
                "name": "To Do",
                "is_done_lane": False,            # optional
                "cards": [
                    {
                        "text": "Set up homelab DNS",
                        "due": "2026-07-01",       # optional, YYYY-MM-DD
                        "priority": "high",         # optional: highest|high|low|lowest
                        "recurrence": None,         # optional, e.g. "every week"
                        "link": None,               # optional — wikilink target instead of plain text
                    },
                    "Plain string cards also work as shorthand",
                ],
            }

        Lane order in the list = left-to-right column order on the board.
        Cards use the same emoji syntax as the Tasks plugin (📅 🔼 🔁 etc.)
        so they remain queryable by tasks_aggregate and Dataview TASK blocks.

        Set is_done_lane=True on exactly one lane (typically the last) to
        mark it as the board's "Complete" lane.
        """
        return kb.create_board(path, title, lanes, tags=tags)

    @server.tool("kanban_create_simple_board")
    def kanban_create_simple_board(
        path: str,
        title: str,
        lane_names: list[str],
        done_lane: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Scaffold an empty Kanban board with just lane headings — no cards yet.

        Use this first when the user wants a board structure before
        populating it, then call kanban_add_card per card. For a board
        with cards already known, prefer kanban_create_board instead —
        it does both steps in a single call.

        Args:
            lane_names: Lane titles in left-to-right order,
                        e.g. ["Backlog", "In Progress", "Done"].
            done_lane: Must exactly match one entry in lane_names.
                       That lane gets the **Complete** marker.
        """
        return kb.create_simple_board(path, title, lane_names, done_lane=done_lane, tags=tags)

    @server.tool("kanban_add_card")
    def kanban_add_card(
        board_path: str,
        lane_name: str,
        text: str,
        due: str | None = None,
        scheduled: str | None = None,
        priority: str | None = None,
        recurrence: str | None = None,
        link: str | None = None,
    ) -> dict[str, Any]:
        """Add one card to a lane on an existing Kanban board.

        Creates the lane at the end of the board if it doesn't exist yet.
        New cards are appended to the bottom of the lane.

        Args:
            priority: highest | high | low | lowest
            link: vault note path to render the card as a wikilink instead
                  of plain text — Kanban shows the linked note's title.
        """
        return kb.add_card(
            board_path, lane_name, text,
            due=due, scheduled=scheduled, priority=priority,
            recurrence=recurrence, link=link,
        )

    @server.tool("kanban_move_card")
    def kanban_move_card(
        board_path: str,
        card_text_fragment: str,
        target_lane: str,
    ) -> dict[str, Any]:
        """Move a card to a different lane, preserving its dates/priority/links.

        Matches the first card whose text contains card_text_fragment
        (case-insensitive substring match).
        """
        return kb.move_card(board_path, card_text_fragment, target_lane)

    @server.tool("kanban_complete_card")
    def kanban_complete_card(board_path: str, card_text_fragment: str) -> dict[str, Any]:
        """Mark a card's checkbox as done in place.

        This does NOT move the card to a "Done" lane — Kanban doesn't do
        that automatically. Call kanban_move_card afterwards if the card
        should visually move to a done/complete lane.
        """
        return kb.complete_card(board_path, card_text_fragment)

    @server.tool("kanban_read_board")
    def kanban_read_board(board_path: str) -> dict[str, Any]:
        """Parse a Kanban board into structured lanes and cards.

        Returns {path, lanes: [{name, is_done_lane, cards: [{text, state, raw}]}]}.
        Use this before kanban_move_card or kanban_add_card if you need to
        inspect current board state first (e.g. to avoid duplicate cards).
        """
        return kb.read_board(board_path)

    @server.tool("kanban_lane_summary")
    def kanban_lane_summary(board_path: str) -> dict[str, int]:
        """Return a quick card-count-per-lane summary for a board.

        Useful for status updates without parsing full card detail.
        """
        return kb.lane_summary(board_path)

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
        """Audit the vault and return notes that are hard to find via search. Uses cached in-memory reads — will not time out.

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
