# Obsidian MCP Permissions And Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local single-user permission profiles and a FastAPI-backed Web UI for operating the Obsidian MCP server.

**Architecture:** Add `obsidian_mcp.permissions` for policy decisions and `obsidian_mcp.web` for API/static UI delivery. Existing `VaultService` and `KnowledgeService` remain the business logic layers, with Web API routes enforcing permission checks before calling them.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, pytest, existing Obsidian MCP service modules, static HTML/CSS/JS.

---

## File Structure

- Create: `src/obsidian_mcp/permissions.py`
- Create: `src/obsidian_mcp/web/__init__.py`
- Create: `src/obsidian_mcp/web/app.py`
- Create: `src/obsidian_mcp/web/static/index.html`
- Create: `src/obsidian_mcp/web/static/styles.css`
- Create: `src/obsidian_mcp/web/static/app.js`
- Modify: `src/obsidian_mcp/config.py`
- Modify: `src/obsidian_mcp/__main__.py`
- Modify: `pyproject.toml`
- Create: `_test_/unit/test_permissions.py`
- Create: `_test_/unit/web/test_app.py`
- Modify: `README.md`, `DOCS/AICONTEXT.md`, `DOCS/codebase_reference.md`, `DOCS/features/permissions-and-web-ui.md`, `agent_logs.md`

## Tasks

### Task 1: Permission Profiles

- [ ] Write failing permission tests for `read_only`, `safe_write`, and `admin` allowed/blocked actions.
- [ ] Run `uv run --extra dev pytest _test_/unit/test_permissions.py -v`; expected failure is missing `obsidian_mcp.permissions`.
- [ ] Implement `PermissionProfile`, `PermissionAction`, `PermissionService`, and `PermissionDeniedError`.
- [ ] Run permission and existing error tests.

### Task 2: Configuration And Dependencies

- [ ] Write failing config tests for `permission_profile`, `web_host`, and `web_port` defaults.
- [ ] Add FastAPI, Uvicorn, and HTTPX dependencies.
- [ ] Extend `ObsidianMCPSettings`.
- [ ] Run config tests.

### Task 3: Web API

- [ ] Write failing Web API tests for status, profile get/update, note listing, read-only update denial, safe-write update success, search, and static index.
- [ ] Run `uv run --extra dev pytest _test_/unit/web/test_app.py -v`; expected failure is missing `obsidian_mcp.web.app`.
- [ ] Implement `create_web_app(settings)` and route handlers.
- [ ] Run Web API tests.

### Task 4: Static Web UI

- [ ] Add static `index.html`, `styles.css`, and `app.js`.
- [ ] Keep UI operational, quiet, accessible, and profile-aware.
- [ ] Ensure controls are disabled by profile state in the UI while backend remains authoritative.

### Task 5: CLI And Docs

- [ ] Add `build_web_app()` and `web_main()` to `__main__.py`.
- [ ] Add console script `obsidian-mcp-web`.
- [ ] Update docs and logs.
- [ ] Run `uv run --extra dev pytest -v`.
- [ ] Run `uv run python -c "from obsidian_mcp.web.app import create_web_app; print(create_web_app)"`.

## Self-Review

- Spec coverage: permissions, FastAPI API, static Web UI, config, tests, and docs are covered.
- Placeholder scan: no placeholders remain.
- Type consistency: names match the approved design.
