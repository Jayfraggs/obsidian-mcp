# AI Context

Last updated: 2026-06-12

## Project State

This workspace is a greenfield Obsidian MCP server project. The root currently contains three prompt files:

- `01_environment_and_architecture.md`: foundation request for a production-grade Python MCP server.
- `02_core_mcp_server_and_tools.md`: core Obsidian note and file tools to implement after the foundation.
- `03_maxed_out_features_and_scaling.md`: advanced knowledge, organization, AI, cache, auth, and UI features for later phases.

There is no Git repository currently initialized in this folder.

## Current Build Strategy

The selected implementation strategy is a staged foundation-first build:

1. Build the environment and architecture foundation from Prompt 1. Completed.
2. Add core MCP note and file tools from Prompt 2. Completed.
3. Add advanced and scaling features from Prompt 3. Local advanced tools completed; platform features deferred.

## Foundation Status

Prompt 1 is implemented as a Python 3.11+ package foundation with:

- MCP SDK integration through a server factory.
- Pydantic-based configuration.
- Centralized logging.
- Explicit application error classes.
- Modular architecture prepared for future tools.
- Type hints and docstrings.
- Tests stored under `_test_`.

Verification passed with `uv run --extra dev pytest -v` and `uv run python -c "from obsidian_mcp.__main__ import build_server; print(build_server)"`.

## Core Tools Status

Prompt 2 is implemented with:

- Core note tools: `read_note`, `create_note`, `update_note`, `append_note`, `delete_note`, `move_note`, and `rename_note`.
- Discovery tools: `search_notes`, `list_files`, and `list_folders`.
- Vault path safety for user-provided paths.
- Metadata extraction for frontmatter, aliases, tags, wiki links, markdown links, task lines, Dataview inline fields, Templater markers, and Excalidraw files.
- Backlink analysis by scanning markdown notes.
- MCP registration through `obsidian_mcp.tools.core.register_core_tools`.

## Advanced Tools Status

Prompt 3 local advanced tools are implemented with:

- Knowledge tools: `build_moc`, `create_atomic_note`, `refactor_large_note`, `suggest_backlinks`, and `auto_tag`.
- PARA and Johnny Decimal suggestion helpers.
- Dataview dashboard note generation.
- Deterministic local semantic-style search.
- Duplicate detection.
- Relationship graph generation.
- Excalidraw architecture note generation.
- MCP registration through `obsidian_mcp.tools.knowledge.register_knowledge_tools`.

Prompt 3 local permissions and Web UI are implemented with:

- Local single-user permission profiles: `read_only`, `safe_write`, and `admin`.
- Backend permission enforcement through `PermissionService`.
- FastAPI Web API and static Web UI served by `obsidian-mcp-web`.

Deferred Prompt 3 platform features remain SQLite metadata cache, multi-user authentication, remote deployment permissions, and remote embedding-backed search.

## Documentation Rules In Use

- `DOCS/codebase_reference.md` tracks project functions as they are created or used.
- `agent_logs.md` records agent actions by category.
- `DOCS/features/` stores one feature document per feature.
- `DOCS/superpowers/specs/` stores design specs before implementation planning.
