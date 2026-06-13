# Obsidian MCP Core Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Prompt 2 core Obsidian note, file, search, metadata, and backlink tools.

**Architecture:** Add a service-backed vault layer below thin MCP tool registrations. Filesystem safety, metadata parsing, note CRUD, search, listing, and backlinks live in `obsidian_mcp.vault`; MCP exposure lives in `obsidian_mcp.tools.core`.

**Tech Stack:** Python 3.11+, MCP SDK, Pydantic, pytest, python-frontmatter, PyYAML, RapidFuzz.

---

## File Structure

- Create: `src/obsidian_mcp/vault/__init__.py` for vault package exports.
- Create: `src/obsidian_mcp/vault/paths.py` for safe vault-relative path resolution.
- Create: `src/obsidian_mcp/vault/metadata.py` for note metadata extraction.
- Create: `src/obsidian_mcp/vault/service.py` for note CRUD, listing, search, and backlinks.
- Create: `src/obsidian_mcp/tools/__init__.py` for tool package exports.
- Create: `src/obsidian_mcp/tools/core.py` for core MCP tool registration.
- Modify: `src/obsidian_mcp/errors.py` to add vault-specific structured errors.
- Modify: `src/obsidian_mcp/__main__.py` to register core tools.
- Create: `_test_/unit/vault/test_paths.py`.
- Create: `_test_/unit/vault/test_metadata.py`.
- Create: `_test_/unit/vault/test_service.py`.
- Create: `_test_/unit/tools/test_core_tools.py`.
- Modify: `DOCS/AICONTEXT.md`, `DOCS/codebase_reference.md`, `DOCS/features/core-mcp-tools.md`, `README.md`, and `agent_logs.md`.

## Tasks

### Task 1: Vault Path Safety

- [ ] Write tests in `_test_/unit/vault/test_paths.py` for note suffix normalization, nested relative paths, rejection of absolute paths, rejection of parent traversal, and rejection of vault escape.
- [ ] Run `uv run --extra dev pytest _test_/unit/vault/test_paths.py -v` and confirm failure because `obsidian_mcp.vault.paths` is missing.
- [ ] Implement `VaultPathResolver` in `src/obsidian_mcp/vault/paths.py`.
- [ ] Run the path tests and confirm they pass.

### Task 2: Vault Errors

- [ ] Extend tests in `_test_/unit/vault/test_paths.py` for invalid path public error code.
- [ ] Run the path tests and confirm failure because vault errors are missing.
- [ ] Extend `src/obsidian_mcp/errors.py` with `VAULT_PATH_INVALID`, `NOTE_NOT_FOUND`, `NOTE_ALREADY_EXISTS`, and `VAULT_OPERATION_FAILED`, plus matching exception classes.
- [ ] Run path and existing error tests and confirm they pass.

### Task 3: Metadata Extraction

- [ ] Write tests in `_test_/unit/vault/test_metadata.py` for frontmatter title, aliases, tags, inline tags, wiki links, markdown links, task lines, Dataview fields, Templater markers, and Excalidraw detection.
- [ ] Run metadata tests and confirm failure because `obsidian_mcp.vault.metadata` is missing.
- [ ] Implement `NoteMetadata` and `extract_note_metadata`.
- [ ] Run metadata tests and confirm they pass.

### Task 4: Note CRUD Service

- [ ] Write tests in `_test_/unit/vault/test_service.py` for `create_note`, `read_note`, `update_note`, `append_note`, `delete_note`, duplicate create rejection, and missing note rejection.
- [ ] Run service tests and confirm failure because `VaultService` is missing.
- [ ] Implement CRUD methods in `src/obsidian_mcp/vault/service.py`.
- [ ] Run service tests and confirm they pass.

### Task 5: Move, Rename, List, Search, Backlinks

- [ ] Extend service tests for `move_note`, `rename_note`, `list_files`, `list_folders`, `search_notes`, and backlink analysis.
- [ ] Run service tests and confirm failure for missing methods.
- [ ] Implement the service methods with bounded deterministic outputs.
- [ ] Run service tests and confirm they pass.

### Task 6: MCP Tool Registration

- [ ] Write tests in `_test_/unit/tools/test_core_tools.py` for registrar adding all ten expected tool names to a fake MCP server.
- [ ] Run tool tests and confirm failure because `obsidian_mcp.tools.core` is missing.
- [ ] Implement `register_core_tools(server, settings)` and wire each tool to `VaultService`.
- [ ] Update `src/obsidian_mcp/__main__.py` to pass `register_core_tools` into `create_server`.
- [ ] Run tool and server tests and confirm they pass.

### Task 7: Documentation And Verification

- [ ] Update `DOCS/AICONTEXT.md` with Stage 2 completion status.
- [ ] Update `DOCS/codebase_reference.md` with new vault and tool functions/classes.
- [ ] Update `DOCS/features/core-mcp-tools.md` with implemented behavior.
- [ ] Update `README.md` with core tool list and configuration usage.
- [ ] Update `agent_logs.md` with implementation and verification entries.
- [ ] Run `uv run --extra dev pytest -v` and confirm all tests pass.
- [ ] Run `uv run python -c "from obsidian_mcp.__main__ import build_server; print(build_server)"` and confirm the import smoke test passes.

## Self-Review

- Spec coverage: all Prompt 2 tools, metadata extraction, backlinks, aliases, tags, and plugin-compatible parsing are covered.
- Placeholder scan: no open placeholders or vague implementation steps remain.
- Type consistency: planned names are consistent across design, tests, and implementation modules.
