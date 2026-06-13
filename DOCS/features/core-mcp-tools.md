# Feature: Core MCP Tools

## Summary

This feature implements the Prompt 2 core Obsidian MCP tools on top of the Prompt 1 foundation.

## Scope

The feature adds note reading, creation, updating, appending, deletion, moving, renaming, searching, file listing, folder listing, metadata extraction, and backlink analysis.

## Architecture Fit

Core tools use a service-backed design:

- `obsidian_mcp.vault.*` modules own vault path safety, metadata extraction, and filesystem behavior.
- `obsidian_mcp.tools.core` owns MCP tool registration.
- `obsidian_mcp.__main__.build_server()` wires core tool registration into the existing server factory.

## Plugin Compatibility

The implementation parses common file patterns used by Dataview, Tasks, Templater, Excalidraw, and Omnisearch-friendly text search. It does not call Obsidian plugin runtime APIs.

## Safety

All paths are vault-relative and must resolve inside the configured vault. Operations reject path traversal, absolute paths, empty paths, duplicate creates, missing files, and invalid destination paths.

## Testing

Tests live under `_test_` and cover path safety, metadata extraction, the service layer, and tool registration behavior.

## Implemented Tool Names

- `read_note`
- `create_note`
- `update_note`
- `append_note`
- `delete_note`
- `move_note`
- `rename_note`
- `search_notes`
- `list_files`
- `list_folders`
