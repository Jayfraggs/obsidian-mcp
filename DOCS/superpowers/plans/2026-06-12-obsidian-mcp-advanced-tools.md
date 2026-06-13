# Obsidian MCP Advanced Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement deterministic local Prompt 3 advanced knowledge tools on top of the existing vault service.

**Architecture:** Add `obsidian_mcp.knowledge.analysis` for pure analysis helpers and `obsidian_mcp.knowledge.service` for high-level note operations. Add `obsidian_mcp.tools.knowledge` as the MCP registration layer and wire it into the existing `build_server()` registrar list.

**Tech Stack:** Python 3.11+, MCP SDK, pytest, RapidFuzz, existing `VaultService` and metadata extraction.

---

## File Structure

- Create: `src/obsidian_mcp/knowledge/__init__.py`
- Create: `src/obsidian_mcp/knowledge/analysis.py`
- Create: `src/obsidian_mcp/knowledge/service.py`
- Create: `src/obsidian_mcp/tools/knowledge.py`
- Modify: `src/obsidian_mcp/__main__.py`
- Create: `_test_/unit/knowledge/test_analysis.py`
- Create: `_test_/unit/knowledge/test_service.py`
- Create: `_test_/unit/tools/test_knowledge_tools.py`
- Modify: `README.md`
- Modify: `DOCS/AICONTEXT.md`
- Modify: `DOCS/codebase_reference.md`
- Modify: `DOCS/features/advanced-knowledge-tools.md`
- Modify: `agent_logs.md`

## Tasks

### Task 1: Analysis Helpers

- [ ] Write failing tests for tokenization, similarity, duplicate detection, PARA classification, Johnny Decimal parsing, tag suggestions, relationship graph generation, Dataview dashboard markdown, and Excalidraw markdown generation.
- [ ] Run `uv run --extra dev pytest _test_/unit/knowledge/test_analysis.py -v`; expected failure is missing `obsidian_mcp.knowledge.analysis`.
- [ ] Implement pure helper functions and dataclasses in `src/obsidian_mcp/knowledge/analysis.py`.
- [ ] Run the analysis tests and confirm they pass.

### Task 2: Knowledge Service

- [ ] Write failing tests for `build_moc`, `create_atomic_note`, `refactor_large_note`, `suggest_backlinks`, `auto_tag`, `semantic_search`, `detect_duplicates`, `build_relationship_graph`, `suggest_para_location`, `suggest_johnny_decimal_location`, `create_dataview_dashboard`, and `generate_excalidraw_architecture`.
- [ ] Run `uv run --extra dev pytest _test_/unit/knowledge/test_service.py -v`; expected failure is missing `KnowledgeService`.
- [ ] Implement `KnowledgeService` in `src/obsidian_mcp/knowledge/service.py` using `VaultService`.
- [ ] Run the service tests and confirm they pass.

### Task 3: MCP Knowledge Tools

- [ ] Write failing tests for registering the Stage 3 MCP tool names and exercising one handler through a fake server.
- [ ] Run `uv run --extra dev pytest _test_/unit/tools/test_knowledge_tools.py -v`; expected failure is missing `obsidian_mcp.tools.knowledge`.
- [ ] Implement `register_knowledge_tools` in `src/obsidian_mcp/tools/knowledge.py`.
- [ ] Wire `register_knowledge_tools` into `build_server()`.
- [ ] Run knowledge tool and server tests and confirm they pass.

### Task 4: Documentation And Verification

- [ ] Update project docs with Stage 3 modules, functions, and behavior.
- [ ] Update `agent_logs.md` with implementation and verification entries.
- [ ] Run `uv run --extra dev pytest -v`; expected result is all tests passing.
- [ ] Run `uv run python -c "from obsidian_mcp.__main__ import build_server; print(build_server)"`; expected result is successful import.

## Self-Review

- Spec coverage: the plan covers knowledge tools, PARA, Johnny Decimal, dashboards, local semantic search, duplicate detection, graphs, Excalidraw generation, MCP registration, docs, and verification.
- Placeholder scan: no unbounded placeholders remain.
- Type consistency: planned names are stable across tests, implementation, and registration.
