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

1. Build the environment and architecture foundation from Prompt 1.
2. Add core MCP note and file tools from Prompt 2.
3. Add advanced and scaling features from Prompt 3.

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

## Documentation Rules In Use

- `DOCS/codebase_reference.md` tracks project functions as they are created or used.
- `agent_logs.md` records agent actions by category.
- `DOCS/features/` stores one feature document per feature.
- `DOCS/superpowers/specs/` stores design specs before implementation planning.
