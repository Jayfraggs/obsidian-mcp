# Codebase Reference

Last updated: 2026-07-20

## Purpose

This document tracks functions, classes, and modules created or used during the project so future work can avoid duplicate implementations and preserve the intended architecture.

## Current Status

Prompt 1 foundation, Prompt 2 core tools, and Prompt 3 local advanced tools have been implemented. Prompt 3 platform features have not been implemented yet.

## Foundation Modules

- `obsidian_mcp.config`: configuration models and loading helpers.
- `obsidian_mcp.logging`: logging setup helpers.
- `obsidian_mcp.errors`: structured application exceptions.
- `obsidian_mcp.server`: MCP server factory and tool registration entry point.
- `obsidian_mcp.__main__`: command-line entry point for running the server.
- `obsidian_mcp.vault.paths`: vault-relative path safety.
- `obsidian_mcp.vault.metadata`: Obsidian markdown metadata extraction.
- `obsidian_mcp.vault.index`: cached backlink index and watchdog update helpers.
- `obsidian_mcp.vault.service`: core vault note, file, search, and backlink operations.
- `obsidian_mcp.tools.core`: MCP registration for core tools.
- `obsidian_mcp.knowledge.analysis`: deterministic local analysis helpers.
- `obsidian_mcp.knowledge.service`: advanced knowledge-management operations.
- `obsidian_mcp.tools.knowledge`: MCP registration for advanced knowledge tools.
- `obsidian_mcp.permissions`: local single-user permission policy profiles.
- `obsidian_mcp.web.app`: FastAPI Web UI application factory and routes.

## Function Registry

### `obsidian_mcp.config`

- `LogLevel`: enum of supported log levels.
- `ObsidianMCPSettings`: Pydantic settings model for vault path, server name, and log level.
- `load_settings() -> ObsidianMCPSettings`: loads settings from environment variables and `.env`.

### `obsidian_mcp.errors`

- `ErrorCode`: enum of stable public application error codes.
- `PublicErrorPayload`: typed dictionary for safe public error payloads.
- `ApplicationError`: base structured application exception.
- `ApplicationError.to_public_dict() -> PublicErrorPayload`: returns a safe public error payload.
- `ConfigurationError`: application exception for invalid configuration.
- `VaultPathError`: application exception for invalid vault-relative paths.
- `NoteNotFoundError`: application exception for missing notes.
- `NoteAlreadyExistsError`: application exception for duplicate note destinations.
- `VaultOperationError`: application exception for failed vault operations.

### `obsidian_mcp.logging`

- `configure_logging(log_level: LogLevel) -> logging.Logger`: configures the package logger.
- `get_logger(name: str) -> logging.Logger`: returns a package child logger.

### `obsidian_mcp.server`

- `ToolRegistrar`: callable type for future tool registration hooks.
- `create_server(settings: ObsidianMCPSettings, tool_registrars: tuple[ToolRegistrar, ...] = ()) -> FastMCP`: creates the MCP server and applies tool registrars.
- `_register_tools(server: FastMCP, settings: ObsidianMCPSettings, tool_registrars: tuple[ToolRegistrar, ...]) -> None`: internal hook used by `create_server`.

### `obsidian_mcp.__main__`

- `build_server() -> FastMCP`: loads settings, configures logging, and creates the server.
- `main() -> None`: runs the configured server.
- `build_web_app()`: loads settings, configures logging, and creates the FastAPI Web UI app.
- `web_main() -> None`: runs the configured local Web UI server.
- `check_config() -> None`: validates local configuration and prints ASCII-safe status output.

### `obsidian_mcp.vault.index`

- `BacklinkIndex`: in-process inverted backlink index with cache-backed startup and watchdog updates.
- `BacklinkIndex.build() -> None`: loads cache or scans markdown files, then persists the index.
- `BacklinkIndex.start() -> None`: starts the watchdog observer for incremental markdown updates.
- `BacklinkIndex.stop() -> None`: stops the observer and flushes pending cache writes.
- `BacklinkIndex.find(target_path: str) -> list[str]`: returns sorted backlink source paths for a target note stem.
- `BacklinkIndex.is_ready() -> bool`: reports whether the index has completed its initial build.
- `_cache_path_for_vault(vault_path: Path) -> Path`: returns the temp-dir cache path for a vault.
- `_extract_link_stems(content: str) -> set[str]`: extracts lowercased wikilink target stems.

### `obsidian_mcp.vault.paths`

- `VaultPathResolver`: resolves vault-relative paths safely.
- `VaultPathResolver.resolve_note_path(relative_path: str | Path) -> Path`: resolves note paths and adds `.md` when missing.
- `VaultPathResolver.resolve_relative_path(relative_path: str | Path) -> Path`: resolves general vault-relative paths.
- `VaultPathResolver.to_vault_relative(path: Path) -> str`: converts an absolute vault path to POSIX-style relative path.

### `obsidian_mcp.vault.metadata`

- `NoteMetadata`: dataclass for extracted note metadata.
- `NoteMetadata.to_dict() -> dict[str, Any]`: serializes metadata for MCP responses.
- `extract_note_metadata(path: str, content: str) -> NoteMetadata`: extracts frontmatter, aliases, tags, links, tasks, Dataview fields, Templater markers, and Excalidraw state.

### `obsidian_mcp.vault.service`

- `VaultService`: service layer for safe Obsidian vault operations.
- `VaultService.create_note(path: str, content: str) -> dict[str, Any]`: creates a markdown note.
- `VaultService.read_note(path: str) -> dict[str, Any]`: reads note content, metadata, and backlinks.
- `VaultService.update_note(path: str, content: str) -> dict[str, Any]`: replaces note content.
- `VaultService.append_note(path: str, content: str) -> dict[str, Any]`: appends note content.
- `VaultService.delete_note(path: str) -> dict[str, Any]`: deletes a note.
- `VaultService.move_note(source: str, destination: str) -> dict[str, str]`: moves a note.
- `VaultService.rename_note(path: str, new_name: str) -> dict[str, str]`: renames a note within its folder.
- `VaultService.list_files() -> list[str]`: lists vault files.
- `VaultService.list_folders() -> list[str]`: lists vault folders.
- `VaultService.search_notes(query: str, limit: int = 10) -> list[dict[str, Any]]`: searches markdown notes.
- `VaultService.find_backlinks(target_path: str) -> list[str]`: finds notes linking to a target note.

### `obsidian_mcp.tools.core`

- `CORE_TOOL_NAMES`: tuple of all Prompt 2 MCP tool names.
- `ToolServer`: protocol for MCP-compatible tool registration.
- `register_core_tools(server: ToolServer, settings: ObsidianMCPSettings) -> None`: registers core tools with a server.

### `obsidian_mcp.knowledge.analysis`

- `NoteDocument`: normalized note data used by local analysis helpers.
- `tokenize(text: str) -> list[str]`: tokenizes text into normalized terms.
- `semantic_rank(query: str, documents: list[NoteDocument], limit: int = 10) -> list[dict[str, Any]]`: ranks notes with token and fuzzy scoring.
- `detect_duplicate_notes(documents: list[NoteDocument], threshold: float = 82) -> list[dict[str, Any]]`: detects likely duplicate notes.
- `classify_para(document: NoteDocument) -> str`: classifies a note into a PARA bucket.
- `parse_johnny_decimal_prefix(path: str) -> dict[str, str | None]`: parses Johnny Decimal prefixes.
- `suggest_tags(document: NoteDocument, existing_tags: list[str], limit: int = 5) -> list[dict[str, Any]]`: suggests tags.
- `build_relationship_graph(documents: list[NoteDocument]) -> dict[str, list[dict[str, Any]]]`: builds relationship graph nodes and edges.
- `build_dataview_dashboard(title: str, tags: list[str]) -> str`: generates Dataview-compatible dashboard markdown.
- `generate_excalidraw_markdown(title: str, graph: dict[str, list[dict[str, Any]]]) -> str`: generates Excalidraw-compatible markdown.

### `obsidian_mcp.knowledge.service`

- `KnowledgeService`: advanced knowledge operations built on `VaultService`.
- `KnowledgeService.build_moc(topic: str, output_path: str | None = None, limit: int = 20) -> dict[str, Any]`: creates a map-of-content note.
- `KnowledgeService.create_atomic_note(...) -> dict[str, Any]`: creates a focused atomic note with frontmatter and source links.
- `KnowledgeService.refactor_large_note(path: str, create_notes: bool = False) -> dict[str, Any]`: returns heading-based split proposals and optionally creates child notes.
- `KnowledgeService.suggest_backlinks(path: str, limit: int = 10) -> list[dict[str, Any]]`: suggests candidate backlinks.
- `KnowledgeService.auto_tag(path: str, limit: int = 5) -> list[dict[str, Any]]`: suggests tags.
- `KnowledgeService.semantic_search(query: str, limit: int = 10) -> list[dict[str, Any]]`: runs deterministic semantic-style search.
- `KnowledgeService.detect_duplicates(threshold: float = 82) -> list[dict[str, Any]]`: detects likely duplicates.
- `KnowledgeService.build_relationship_graph() -> dict[str, list[dict[str, Any]]]`: builds a relationship graph for the vault.
- `KnowledgeService.suggest_para_location(path: str) -> dict[str, str]`: suggests a PARA location.
- `KnowledgeService.suggest_johnny_decimal_location(path: str) -> dict[str, str | None]`: returns Johnny Decimal prefix details.
- `KnowledgeService.create_dataview_dashboard(path: str, title: str, tags: list[str] | None = None) -> dict[str, Any]`: creates a Dataview dashboard note.
- `KnowledgeService.generate_excalidraw_architecture(path: str, title: str = "Architecture") -> dict[str, Any]`: creates an Excalidraw architecture note.

### `obsidian_mcp.tools.knowledge`

- `KNOWLEDGE_TOOL_NAMES`: tuple of all Prompt 3 local MCP tool names.
- `register_knowledge_tools(server: ToolServer, settings: ObsidianMCPSettings) -> None`: registers advanced knowledge tools with a server.

### `obsidian_mcp.permissions`

- `PermissionProfile`: enum of `read_only`, `safe_write`, and `admin`.
- `PermissionAction`: enum of permission-checked application actions.
- `PermissionService`: evaluates allowed and blocked actions for a profile.
- `PermissionService.is_allowed(action: PermissionAction) -> bool`: returns whether an action is allowed.
- `PermissionService.require(action: PermissionAction) -> None`: raises `PermissionDeniedError` when blocked.
- `PermissionService.summary() -> dict[str, list[str] | str]`: returns allowed and blocked action names.

### `obsidian_mcp.web.app`

- `create_web_app(settings: ObsidianMCPSettings) -> FastAPI`: creates the local Web UI application.
- `ProfileUpdateRequest`: API model for permission profile updates.
- `NoteContentRequest`: API model for note writes.
- `MOCRequest`: API model for MOC creation.
- `AtomicNoteRequest`: API model for atomic note creation.
- `DashboardRequest`: API model for Dataview dashboard creation.

---

## Setup & Launcher Scripts (repo root)

Added 2026-09-20. These are standalone scripts, not part of the `obsidian_mcp`
package. They have no import relationship with `src/` — they invoke the server
as a subprocess via `uv run obsidian-mcp`.

### `setup_wizard.py`

- `get_os() -> str`: Returns `"windows"`, `"mac"`, or `"linux"`.
- `get_claude_desktop_config_path() -> Path | None`: OS-specific path to `claude_desktop_config.json`.
- `get_project_root() -> Path`: Directory of `setup_wizard.py` (repo root).
- `get_env_path() -> Path`: `project_root / ".env"`.
- `get_uv_exe() -> str | None`: `shutil.which("uv")`.
- `write_env(fields: dict[str, str]) -> None`: Writes `.env` file with header.
- `merge_claude_desktop_config(server_command: list[str], env_vars: dict[str, str]) -> tuple[bool, str]`: Merge-safe update of Claude Desktop JSON config. Atomic write via `.tmp` rename.
- `install_uv() -> tuple[bool, str]`: Runs official uv installer for current OS.
- `run_uv_sync(log_callback: Callable) -> tuple[bool, str]`: Runs `uv sync`, streams output to callback.
- `create_desktop_shortcut(server_mode: bool = False) -> bool`: Creates OS-native desktop shortcut to wizard or launcher.
- `_note_matches_exception(...)`: Internal — checks a single exception rule against a note. (In `vault/service.py`.)
- `SetupWizard(ctk.CTk)`: 7-step GUI wizard. Methods: `_show_step`, `_go_next`, `_go_back`, `_validate_step`, `_page_*`, `_run_install`, `_build_env_dict`, `_build_server_command`.

### `server_launcher.py`

- `get_os() -> str`: Same as above (duplicated for script independence).
- `get_project_root() -> Path`: Directory of `server_launcher.py`.
- `get_uv_exe() -> str`: Returns path or `"uv"` fallback string.
- `build_server_command() -> list[str]`: `[uv, "--directory", root, "run", "obsidian-mcp"]`.
- `_make_tray_image(color: str) -> PIL.Image`: Draws 64×64 tray icon programmatically.
- `ServerProcess`: Subprocess manager. Methods: `start`, `stop`, `restart`, `is_running`. Callbacks: `on_log(str)`, `on_status_change(str)`. Status values: `"stopped"`, `"running"`, `"error"`.
- `StatusPanel(ctk.CTkToplevel)`: Floating status window. Thread-safe methods: `append_log(str)`, `update_status(str)`. `_on_close` withdraws instead of destroying.
- `TrayController`: Owns root, icon, panel. `run()` blocks until quit. `_open_panel` always dispatches to tkinter thread via `root.after`.

### `_test_/unit/test_setup_wizard.py`

- 31 tests covering OS detection, config path resolution, `.env` write,
  Claude Desktop JSON merge (including merge-safety and atomic write),
  server command construction, `ServerProcess` lifecycle, desktop shortcut
  creation per OS, `install_uv`, and `run_uv_sync`.
- All GUI modules mocked at import time — tests are fully headless.

### `vault/service.py` additions (2026-09-20)

- `ExceptionRule`: `TypedDict` with keys `type: str` and `value: str`. Valid types: `folder`, `tag`, `frontmatter`, `path_glob`, `contains_string`.
- `_note_matches_exception(vault_rel, content, rules) -> tuple[bool, str]`: Returns `(True, reason)` if any rule matches (OR logic), `(False, "")` otherwise.
- `_build_search_pattern(old_str, *, whole_word, case_sensitive) -> re.Pattern`: Compiles search pattern. `whole_word=True` uses `(?<![A-Za-z0-9\-])..(?![A-Za-z0-9\-])` lookarounds (safe for hyphenated identifiers like `DeepSeek-V4-Flash`).
- `_apply_replacement(content, pattern, new_str, *, require_unique_per_note) -> tuple[str | None, str | None]`: Returns `(new_content, None)` on success, `(None, None)` if no match, `(None, reason)` if ambiguous.
- `VaultService.str_replace_vault(...)`: Extended with `whole_word`, `case_sensitive`, `dry_run`, `backup`, `exception_rules` parameters. Returns `{dry_run, updated, skipped, ambiguous, unchanged_count, backup_dir}`.
- `VaultService._backup_note(vault_rel, content, backup_root)`: Writes note content to `.mcp-backups/<timestamp>/<vault_rel>` before overwriting.
- Backup directory constant: `_BACKUP_DIR = ".mcp-backups"`.
