# Obsidian MCP Core Tools Design

Date: 2026-06-12

## Decision

Implement Prompt 2 with a service-backed tool layer. Vault file behavior will live in focused services, and MCP handlers will remain thin registration wrappers around those services.

## Goals

- Implement core note tools: `read_note`, `create_note`, `update_note`, `append_note`, `delete_note`, `move_note`, and `rename_note`.
- Implement discovery tools: `search_notes`, `list_files`, and `list_folders`.
- Add metadata extraction for YAML frontmatter, aliases, tags, wiki links, markdown links, backlinks, task lines, Dataview-style inline fields, Templater markers, and Excalidraw files.
- Register the tools through the Stage 1 `create_server(..., tool_registrars=...)` hook.
- Keep all file operations constrained to the configured vault path.

## Non-Goals

- No SQLite cache, embedding search, semantic search, relationship graphs, FastAPI, authentication, permissions, or Web UI.
- No dependency on Obsidian plugin runtime APIs. Dataview, Tasks, Templater, Excalidraw, and Omnisearch support means parsing compatible file patterns from disk.
- No destructive file operations outside the configured vault root.

## Architecture

Stage 2 adds these package areas:

- `obsidian_mcp.vault.paths`: path normalization, note-path resolution, and vault escape prevention.
- `obsidian_mcp.vault.metadata`: markdown/frontmatter metadata extraction.
- `obsidian_mcp.vault.service`: note CRUD, move/rename, listing, searching, and backlink lookup.
- `obsidian_mcp.tools.core`: MCP tool registration for the core tools.

The service layer depends on settings and pure filesystem operations. The tool layer depends on the service layer and MCP SDK. This preserves separation between MCP protocol registration and business logic.

## Data Flow

1. `build_server()` loads settings and configures logging.
2. `build_server()` passes the core tool registrar to `create_server()`.
3. The registrar creates a `VaultService` from the configured vault path.
4. MCP tool handlers call service methods.
5. Service methods validate paths, perform deterministic file operations, and return dictionaries or lists suitable for MCP serialization.

## File Safety

All user-supplied paths are treated as vault-relative paths. The path layer will reject absolute paths, parent traversal, empty paths, and resolved paths outside the vault. Note operations will use `.md` files; callers can pass either `name` or `name.md`.

## Error Handling

Stage 2 will extend structured errors with vault-specific codes such as invalid path, not found, already exists, and operation failed. Public payloads will keep stable codes and safe messages. Internal path details stay on exception objects only.

## Metadata

Metadata extraction will parse:

- YAML frontmatter through `python-frontmatter`.
- `aliases` and `tags` from frontmatter.
- Inline hashtag tags from markdown body.
- Wiki links such as `[[Note]]` and aliased links such as `[[Note|Label]]`.
- Markdown links such as `[label](path.md)`.
- Backlinks by scanning notes that link to the requested note stem.
- Task lines compatible with the Tasks plugin, such as `- [ ] task`.
- Dataview inline fields such as `key:: value`.
- Templater markers such as `<% ... %>`.
- Excalidraw files by `.excalidraw.md` suffix or Excalidraw frontmatter marker.

## Search

`search_notes` will perform deterministic text search over markdown files using case-insensitive matching and RapidFuzz ranking. It will return bounded results with path, score, and matching preview.

## Testing

Tests remain under `_test_`. Stage 2 will use TDD for:

- path safety and note path normalization.
- metadata extraction.
- CRUD operations.
- move, rename, list, and search operations.
- MCP registrar integration.

## Documentation

Stage 2 will update:

- `DOCS/AICONTEXT.md`
- `DOCS/codebase_reference.md`
- `DOCS/features/core-mcp-tools.md`
- `agent_logs.md`
- `README.md`

## Rollout

1. Add failing tests for vault paths and errors.
2. Implement path and error foundations.
3. Add failing metadata tests and implementation.
4. Add failing CRUD/list/search tests and implementation.
5. Add failing MCP registration tests and implementation.
6. Run full verification and update docs.
