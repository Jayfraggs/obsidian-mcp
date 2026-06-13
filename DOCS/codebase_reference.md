# Codebase Reference

Last updated: 2026-06-12

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
