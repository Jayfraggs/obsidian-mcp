# Codebase Reference

Last updated: 2026-06-12

## Purpose

This document tracks functions, classes, and modules created or used during the project so future work can avoid duplicate implementations and preserve the intended architecture.

## Current Status

Prompt 1 foundation production code has been created. Prompt 2 tools and Prompt 3 advanced features have not been implemented yet.

## Foundation Modules

- `obsidian_mcp.config`: configuration models and loading helpers.
- `obsidian_mcp.logging`: logging setup helpers.
- `obsidian_mcp.errors`: structured application exceptions.
- `obsidian_mcp.server`: MCP server factory and tool registration entry point.
- `obsidian_mcp.__main__`: command-line entry point for running the server.

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
