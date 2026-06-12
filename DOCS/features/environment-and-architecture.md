# Feature: Environment And Architecture Foundation

## Summary

This feature establishes the production-grade foundation for an Obsidian MCP server before note tools or advanced features are added.

## Scope

The foundation provides a Python 3.11+ package with configuration, logging, explicit error handling, a modular MCP server factory, type hints, docstrings, and tests.

## Fit In The Codebase

The foundation is the base layer for all later phases:

- Prompt 2 tools will register through the server factory and use shared configuration, logging, and errors.
- Prompt 3 advanced features will build on the same architecture without rewriting the server startup path.

## Implemented Modules

- `obsidian_mcp.config`: Pydantic settings and environment loading.
- `obsidian_mcp.errors`: safe public error payloads and stable error codes.
- `obsidian_mcp.logging`: package logger configuration.
- `obsidian_mcp.server`: MCP server factory and future tool registrar hook.
- `obsidian_mcp.__main__`: CLI build and run entry point.

## Boundaries

This feature does not implement note CRUD tools, search, Dataview, Tasks, Templater, Excalidraw, Omnisearch, semantic search, authentication, SQLite caching, FastAPI, or a Web UI. Those features belong to later stages.

## Testing Expectations

Tests live under `_test_` and cover configuration validation, logging setup, error serialization, and server creation. Verification passed with 10 tests.
