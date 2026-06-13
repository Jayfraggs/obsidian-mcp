# Obsidian MCP Advanced Tools Design

Date: 2026-06-12

## Decision

Implement Prompt 3 as a deterministic local advanced-tools stage. This stage adds knowledge management, organization, dashboard, graph, duplicate, and Excalidraw-generation tools without introducing remote AI calls, FastAPI, SQLite cache, authentication, permissions, or Web UI yet.

## Goals

- Implement knowledge tools:
  - `build_moc`
  - `create_atomic_note`
  - `refactor_large_note`
  - `suggest_backlinks`
  - `auto_tag`
- Add PARA support for Projects, Areas, Resources, and Archives.
- Add Johnny Decimal support for numbered folder validation and suggestions.
- Generate Dataview dashboard notes.
- Add local AI-adjacent features:
  - semantic-style search using deterministic token and fuzzy scoring.
  - duplicate detection.
  - relationship graph generation.
- Generate Excalidraw architecture notes from local note relationships.
- Register Stage 3 tools through the existing MCP server registrar pattern.

## Non-Goals

- No OpenAI API or remote embedding calls in this stage.
- No FastAPI server.
- No SQLite metadata cache.
- No authentication or permissions system.
- No Web UI.
- No destructive bulk rewrite of user notes. Refactoring tools will return proposals and optionally create new notes only through explicit service calls.

## Architecture

Stage 3 adds:

- `obsidian_mcp.knowledge.analysis`: reusable tokenization, similarity, duplicate, graph, and tag helpers.
- `obsidian_mcp.knowledge.service`: high-level knowledge operations that compose `VaultService`.
- `obsidian_mcp.tools.knowledge`: MCP registration for advanced tools.

The existing `VaultService` remains the filesystem boundary. Knowledge services use Stage 2 metadata, search, list, read, and create/update behavior rather than duplicating vault logic.

## Tool Behavior

### `build_moc`

Builds a map-of-content markdown note for a topic. It finds related notes by tags, links, title/path terms, and content similarity. It writes or returns a structured MOC containing grouped links and source metadata.

### `create_atomic_note`

Creates a small focused note with frontmatter, aliases, tags, source links, and content. It enforces a single-note path and uses `VaultService.create_note`.

### `refactor_large_note`

Analyzes a long note and returns split suggestions based on headings. It can create child atomic notes when explicitly requested through a `create_notes` flag. Default behavior is proposal-only to avoid destructive edits.

### `suggest_backlinks`

Suggests candidate backlinks for a note using token similarity, shared tags, and related links. Existing backlinks are excluded.

### `auto_tag`

Suggests tags from existing vault tags and note content. It returns suggestions with scores and does not mutate the note by default.

## PARA Support

PARA behavior classifies notes into Projects, Areas, Resources, or Archives using tags, folder path, and content terms. The implementation will support suggestions and optional note creation under PARA folders.

## Johnny Decimal Support

Johnny Decimal behavior validates folder prefixes such as `10-19`, `11 Notes`, and `11.01 Topic`. It can suggest target folders for notes based on existing numbered areas.

## Dataview Dashboards

Dashboard generation creates markdown notes containing Dataview query blocks for tags, PARA sections, recently changed files, task summaries, and MOC links. It writes normal markdown compatible with the Dataview plugin, without requiring Dataview runtime APIs.

## Local Semantic Features

Semantic-style search uses deterministic local scoring:

- tokenize note title, path, tags, aliases, headings, and body text.
- combine token overlap and RapidFuzz similarity.
- return bounded ranked results.

Duplicate detection uses title similarity, normalized body similarity, aliases, and tags. Relationship graphs use wiki links, markdown links, backlinks, tags, and duplicate/similarity edges.

## Excalidraw Architecture Generation

Excalidraw generation creates `.excalidraw.md` files containing a valid Excalidraw-compatible JSON block embedded in markdown. Nodes represent notes or conceptual modules, and edges represent links or relationships.

## Error Handling

Stage 3 reuses structured application errors. New operations must fail explicitly with safe public messages. Tools must not silently skip invalid source notes, invalid destination paths, or failed writes.

## Testing

Tests remain under `_test_`. Stage 3 will use test-first development for:

- token and similarity helpers.
- MOC generation.
- atomic note creation.
- large note refactor proposals.
- backlink and tag suggestions.
- PARA and Johnny Decimal suggestions.
- Dataview dashboard markdown generation.
- duplicate detection and relationship graph output.
- Excalidraw markdown generation.
- MCP tool registration.

## Documentation

Stage 3 will update:

- `DOCS/AICONTEXT.md`
- `DOCS/codebase_reference.md`
- `DOCS/features/advanced-knowledge-tools.md`
- `README.md`
- `agent_logs.md`

## Future Extension Points

The following Prompt 3 items stay documented for later implementation:

- FastAPI
- SQLite metadata cache
- authentication
- permissions
- Web UI
- remote embedding-backed semantic search

These need separate specs because they introduce network/API surfaces, persistence, security boundaries, and UI architecture.
