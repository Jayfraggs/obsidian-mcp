# Feature: Permissions And Web UI

## Summary

This feature adds local single-user permission profiles and a FastAPI-backed Web UI for operating the Obsidian MCP server from a browser.

## Scope

- Local permission profiles: `read_only`, `safe_write`, and `admin`.
- Backend permission enforcement through a shared permission service.
- FastAPI app factory and API routes for status, permissions, notes, search, and selected knowledge tools.
- Static HTML/CSS/JS UI served from the Python app.

## Architecture Fit

- `obsidian_mcp.permissions` owns permission policy decisions.
- `obsidian_mcp.web.app` owns FastAPI route wiring.
- `obsidian_mcp.web.static` contains browser assets.
- Existing `VaultService` and `KnowledgeService` remain the business logic layers.

## Security Notes

This is a local single-user policy system, not authentication. It protects local operations from accidental or UI-triggered unsafe actions. It is not a substitute for multi-user auth or remote deployment security.

## Testing

Tests live under `_test_` and cover permission decisions plus Web API behavior.

## Run Command

Use `obsidian-mcp-web` or:

```powershell
uv run obsidian-mcp-web
```
