# Feature: Advanced Knowledge Tools

## Summary

This feature implements the local advanced knowledge-management portion of Prompt 3 on top of the Stage 1 foundation and Stage 2 core vault tools.

## Scope

The feature adds MOC building, atomic note creation, large-note refactor proposals, backlink suggestions, auto-tag suggestions, PARA organization helpers, Johnny Decimal helpers, Dataview dashboard generation, deterministic semantic-style search, duplicate detection, relationship graphs, and Excalidraw architecture note generation.

## Architecture Fit

- `obsidian_mcp.knowledge.analysis` will contain reusable deterministic analysis helpers.
- `obsidian_mcp.knowledge.service` will contain high-level knowledge operations.
- `obsidian_mcp.tools.knowledge` will register Stage 3 MCP tools.
- `obsidian_mcp.vault.service.VaultService` remains the filesystem and note-operation boundary.

## Deferred Features

FastAPI, SQLite metadata cache, authentication, permissions, Web UI, and remote embedding-backed semantic search are future extension points and are not part of the local advanced-tools implementation.

## Safety

Default behavior avoids destructive note rewrites. Refactor and suggestion tools return proposals by default; note creation or dashboard generation happens through explicit create/write operations.

## Testing

Tests live under `_test_` and cover analysis helpers, knowledge service behavior, generated markdown, generated Excalidraw content, and MCP registration.

## Implemented Tool Names

- `build_moc`
- `create_atomic_note`
- `refactor_large_note`
- `suggest_backlinks`
- `auto_tag`
- `semantic_search`
- `detect_duplicates`
- `build_relationship_graph`
- `suggest_para_location`
- `suggest_johnny_decimal_location`
- `create_dataview_dashboard`
- `generate_excalidraw_architecture`
