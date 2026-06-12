# Obsidian MCP Foundation Design

Date: 2026-06-12

## Decision

Use a staged foundation-first build. Implement Prompt 1 first, then layer Prompt 2 tools on top of that foundation, then implement Prompt 3 advanced and scaling features.

## Goals

- Create a production-grade Python 3.11+ project skeleton for an Obsidian MCP server.
- Use the MCP SDK, Pydantic, watchdog, rapidfuzz, frontmatter, and PyYAML as declared dependencies.
- Provide modular configuration, logging, error handling, tests, type hints, and docstrings.
- Keep the architecture ready for Prompt 2 tool registration without implementing those tools in the first stage.

## Non-Goals

- No note CRUD tools in the foundation stage.
- No Obsidian vault indexing, backlink analysis, Dataview, Tasks, Templater, Excalidraw, or Omnisearch support yet.
- No advanced Prompt 3 features such as semantic search, duplicate detection, FastAPI, SQLite cache, authentication, permissions, or Web UI.

## Architecture

The project will use a `src/obsidian_mcp` package with clear module boundaries:

- `config`: Pydantic settings models and configuration loading.
- `logging`: centralized structured logging setup.
- `errors`: explicit exception types and safe error payloads.
- `server`: MCP server factory and future tool registration hook.
- `__main__`: command-line entry point.

This separates startup, configuration, error behavior, and future tool registration so later phases can add tool modules without rewriting the foundation.

## Configuration

Configuration will be environment-driven and validated with Pydantic. The foundation will define settings for the Obsidian vault path, log level, optional server name, and future extension fields. Invalid configuration must fail fast with clear errors.

## Logging

Logging will be centralized in one module. Production code will not use ad hoc `print` or `console` style output. Log level will come from validated configuration.

## Error Handling

The foundation will define structured application errors with stable error codes and safe public messages. Internal details must not leak through public error payloads.

## Testing

Tests will live under `_test_` as requested. The foundation will use test-first development for production behavior. Initial tests will cover configuration validation, logging setup, error payloads, and server factory behavior.

## Documentation

The project will maintain:

- `DOCS/AICONTEXT.md` for current project context.
- `DOCS/codebase_reference.md` for function and module tracking.
- `DOCS/features/environment-and-architecture.md` for this feature.
- `agent_logs.md` for action logging.

## Rollout

1. Implement Prompt 1 foundation.
2. Verify tests and import behavior.
3. Update documentation and logs.
4. Start Prompt 2 tool implementation from the same architecture.
