# Agent Logs

## 2026-06-12 - Context And Planning

- Reviewed the available prompt files and identified the workspace as a greenfield Obsidian MCP server project.
- Confirmed the implementation sequence with the user: Prompt 1 foundation, Prompt 2 tools, then Prompt 3 advanced features.
- Selected the staged foundation-first build approach.

## 2026-06-12 - Documentation

- Created `DOCS/AICONTEXT.md` to capture current project context.
- Created `DOCS/codebase_reference.md` to track future functions, classes, and modules.
- Created `DOCS/features/environment-and-architecture.md` for the foundation feature.
- Created `DOCS/superpowers/specs/2026-06-12-obsidian-mcp-foundation-design.md` for the approved foundation design.

## 2026-06-12 - Implementation Planning

- Created `DOCS/superpowers/plans/2026-06-12-obsidian-mcp-foundation.md` for the Prompt 1 foundation implementation.
- Confirmed no Git worktree can be created because the workspace is not a Git repository.

## 2026-06-12 - Tests

- Added the first failing configuration import test in `_test_/unit/test_config.py`.
- Verified the first configuration import test failed because `obsidian_mcp` did not exist.
- Verified the first configuration import test passed after adding package metadata and a minimal package.
- Expanded configuration tests for safe defaults, environment loading, and missing vault path validation.
- Verified the expanded configuration tests failed because `LogLevel` and `load_settings` were missing.

## 2026-06-12 - Configuration

- Implemented `LogLevel`, `ObsidianMCPSettings`, and `load_settings` in `src/obsidian_mcp/config.py`.
- Added Pydantic validation requiring the Obsidian vault path to exist and be a directory.
- Configuration green verification is pending because the test command was blocked by the approval/usage gate.

## 2026-06-12 - Errors

- Added `_test_/unit/test_errors.py` for safe public error payloads and stable configuration error codes.
- Implemented `ErrorCode`, `PublicErrorPayload`, `ApplicationError`, and `ConfigurationError`.

## 2026-06-12 - Logging

- Added `_test_/unit/test_logging.py` for centralized package logging behavior.
- Implemented `configure_logging` and `get_logger` in `src/obsidian_mcp/logging.py`.

## 2026-06-12 - Server

- Added `_test_/unit/test_server.py` for MCP server creation and CLI build behavior.
- Implemented `create_server` and the private tool registration hook in `src/obsidian_mcp/server.py`.
- Implemented `build_server` and `main` in `src/obsidian_mcp/__main__.py`.

## 2026-06-12 - Documentation Updates

- Updated `DOCS/AICONTEXT.md` to reflect the implemented Prompt 1 foundation.
- Updated `DOCS/codebase_reference.md` with the created modules, classes, functions, and type aliases.
- Updated `DOCS/features/environment-and-architecture.md` with implemented foundation modules.
- Updated `README.md` with current status and usage commands.

## 2026-06-12 - Verification

- Ran `uv run --extra dev pytest -v`; all 10 tests passed.
- Ran `uv run python -c "from obsidian_mcp.__main__ import build_server; print(build_server)"`; import smoke test passed.
- Updated documentation to remove pending verification language.

## 2026-06-12 - Stage 2 Planning

- Started Prompt 2 core MCP tools planning.
- Reviewed `DOCS/AICONTEXT.md`, `DOCS/codebase_reference.md`, `02_core_mcp_server_and_tools.md`, and Stage 1 source modules.
- Identified `create_server(..., tool_registrars=...)` as the integration point for Stage 2 tool registration.
- Wrote the Stage 2 design spec at `DOCS/superpowers/specs/2026-06-12-obsidian-mcp-core-tools-design.md`.
- Created the Stage 2 feature document at `DOCS/features/core-mcp-tools.md`.

## 2026-06-12 - Stage 2 Tests

- Added failing vault path safety tests in `_test_/unit/vault/test_paths.py`.
- Verified vault path tests failed because `VaultPathError` and vault modules were missing.

## 2026-06-12 - Stage 2 Vault Paths

- Added vault-specific structured errors to `src/obsidian_mcp/errors.py`.
- Created the `obsidian_mcp.vault` package.
- Implemented `VaultPathResolver` for safe vault-relative path resolution.
- Verified vault path and error tests passed.
- Added failing metadata extraction tests in `_test_/unit/vault/test_metadata.py`.
- Verified metadata tests failed because `obsidian_mcp.vault.metadata` was missing.

## 2026-06-12 - Stage 2 Metadata

- Implemented `NoteMetadata` and `extract_note_metadata` in `src/obsidian_mcp/vault/metadata.py`.
- Added parsing for frontmatter, aliases, tags, wiki links, markdown links, tasks, Dataview fields, Templater markers, and Excalidraw markers.
- Verified metadata tests passed.
- Added failing `VaultService` tests for CRUD, move, rename, list, search, and backlinks.
- Verified service tests failed because `obsidian_mcp.vault.service` was missing.

## 2026-06-12 - Stage 2 Vault Service

- Implemented `VaultService` with note CRUD, move, rename, file listing, folder listing, fuzzy search, and backlink lookup.
- Verified `VaultService` tests passed.
- Added failing MCP core tool registration tests in `_test_/unit/tools/test_core_tools.py`.
- Verified core tool tests failed because `obsidian_mcp.tools` was missing.

## 2026-06-12 - Stage 2 MCP Tools

- Created the `obsidian_mcp.tools` package.
- Implemented `register_core_tools` and `CORE_TOOL_NAMES` in `src/obsidian_mcp/tools/core.py`.
- Wired `register_core_tools` into `build_server()`.
- Verified core tool registration and server integration tests passed.

## 2026-06-12 - Stage 2 Documentation Updates

- Updated `DOCS/AICONTEXT.md` with Prompt 2 implementation status.
- Updated `DOCS/codebase_reference.md` with Stage 2 modules, classes, and functions.
- Updated `DOCS/features/core-mcp-tools.md` with implemented tool names.
- Updated `README.md` with core tool documentation.

## 2026-06-12 - Stage 2 Verification

- Ran `uv run --extra dev pytest -v`; all 27 tests passed.
- Ran `uv run python -c "from obsidian_mcp.__main__ import build_server; print(build_server)"`; import smoke test passed.

## 2026-06-12 - Stage 3 Planning

- Reviewed Stage 3 prompt, current project context, codebase reference, action logs, and dependency configuration.
- Selected deterministic local advanced tools as the Stage 3 implementation scope.
- Deferred FastAPI, SQLite cache, authentication, permissions, Web UI, and remote embedding-backed semantic search to later specs.
- Wrote `DOCS/superpowers/specs/2026-06-12-obsidian-mcp-advanced-tools-design.md`.
- Created `DOCS/features/advanced-knowledge-tools.md`.

## 2026-06-12 - Stage 3 Implementation Planning

- Created `DOCS/superpowers/plans/2026-06-12-obsidian-mcp-advanced-tools.md`.
- Started Stage 3 test-first implementation with analysis helper tests.
- Verified analysis tests failed because `obsidian_mcp.knowledge` was missing.

## 2026-06-12 - Stage 3 Analysis

- Created the `obsidian_mcp.knowledge` package.
- Implemented deterministic analysis helpers for tokenization, ranking, duplicates, PARA, Johnny Decimal, tags, graphs, Dataview dashboards, and Excalidraw markdown.
- Verified analysis helper tests passed.
- Added failing knowledge service tests for Stage 3 user-facing operations.
- Verified knowledge service tests failed because `KnowledgeService` was missing.

## 2026-06-12 - Stage 3 Knowledge Service

- Implemented `KnowledgeService` with MOC generation, atomic notes, refactor proposals, backlink/tag suggestions, local semantic search, duplicates, relationship graph, PARA, Johnny Decimal, Dataview dashboard creation, and Excalidraw generation.
- Verified knowledge service tests passed.
- Added failing Stage 3 MCP knowledge tool registration tests.
- Verified Stage 3 MCP knowledge tool tests failed because `obsidian_mcp.tools.knowledge` was missing.

## 2026-06-12 - Stage 3 MCP Tools

- Implemented `register_knowledge_tools` and `KNOWLEDGE_TOOL_NAMES` in `src/obsidian_mcp/tools/knowledge.py`.
- Wired Stage 3 knowledge tools into `build_server()`.
- Verified Stage 3 knowledge tool registration and server integration tests passed.

## 2026-06-12 - Stage 3 Documentation Updates

- Updated `DOCS/AICONTEXT.md` with local Prompt 3 implementation status.
- Updated `DOCS/codebase_reference.md` with Stage 3 modules, classes, and functions.
- Updated `DOCS/features/advanced-knowledge-tools.md` with implemented Stage 3 tool names.
- Updated `README.md` with advanced knowledge tool documentation.

## 2026-06-12 - Stage 3 Verification Debugging

- Full pytest collection failed because duplicate test basenames were imported as top-level modules.
- Updated pytest configuration to use `--import-mode=importlib`, preventing module-name collisions during collection.

## 2026-06-12 - Stage 3 Verification

- Ran `uv run --extra dev pytest -v`; all 44 tests passed.
- Ran `uv run python -c "from obsidian_mcp.__main__ import build_server; print(build_server)"`; import smoke test passed.

## 2026-06-12 - Permissions And Web UI Planning

- Started local single-user permission profiles and FastAPI Web UI design.
- Confirmed the user selected single-user policy profiles instead of multi-user login.
- Wrote `DOCS/superpowers/specs/2026-06-12-obsidian-mcp-permissions-web-ui-design.md`.
- Created `DOCS/features/permissions-and-web-ui.md`.
- Created `DOCS/superpowers/plans/2026-06-12-obsidian-mcp-permissions-web-ui.md`.

## 2026-06-12 - Permissions Tests

- Added failing permission policy tests in `_test_/unit/test_permissions.py`.
- Verified permission tests failed because `obsidian_mcp.permissions` was missing.

## 2026-06-12 - Permissions Implementation

- Added `PERMISSION_DENIED` and `PermissionDeniedError`.
- Implemented `PermissionProfile`, `PermissionAction`, and `PermissionService`.
- Verified permission and error tests passed.
- Added configuration tests for permission profile and Web UI host/port settings.
- Verified configuration tests failed because permission and Web UI settings were missing.

## 2026-06-12 - Web UI Configuration

- Added FastAPI, Uvicorn, and HTTPX dependency entries.
- Added `obsidian-mcp-web` console script entry.
- Extended settings with `permission_profile`, `web_host`, and `web_port`.
- Verified Web UI configuration tests passed.
- Added failing FastAPI Web API tests in `_test_/unit/web/test_app.py`.
- Verified Web API tests failed because `obsidian_mcp.web` was missing.

## 2026-06-12 - Web API And Static UI

- Implemented `create_web_app` with FastAPI routes for status, permissions, notes, search, selected knowledge tools, and static index serving.
- Added static Web UI assets in `src/obsidian_mcp/web/static`.
- Verified Web API tests passed.
- Added `build_web_app` and `web_main` entry points.

## 2026-06-12 - Permissions And Web UI Documentation Updates

- Updated `DOCS/AICONTEXT.md` with permissions and Web UI implementation status.
- Updated `DOCS/codebase_reference.md` with permission and Web modules.
- Updated `DOCS/features/permissions-and-web-ui.md` with run command.
- Updated `README.md` with local Web UI usage and configuration.

## 2026-06-12 - Permissions And Web UI Verification

- Ran `uv run --extra dev pytest -v`; all 53 tests passed with one upstream FastAPI/Starlette deprecation warning.
- Ran `uv run python -c "from obsidian_mcp.web.app import create_web_app; from obsidian_mcp.__main__ import build_web_app; print(create_web_app, build_web_app)"`; import smoke test passed.

## 2026-06-12 - Foundation Packaging

- Created `pyproject.toml` with Python package metadata, dependencies, pytest configuration, and tooling defaults.
- Created `.gitignore` for Python, environment, test, and build artifacts.
- Created the initial `src/obsidian_mcp` package and minimal configuration module.
- Added `README.md` after the package build reported the referenced readme was missing.

## 2026-07-20 - Backlink Startup and CLI Check Fix

### Investigation

- Reproduced the startup regression with a focused backlink index test.
- Identified that `BacklinkIndex._persist_now` had been dedented out of the class, leaving helper methods such as `_rel` unreachable as instance methods.
- Ran `python -m obsidian_mcp check` and found a separate Windows console encoding failure caused by Unicode check/cross status glyphs.

### Code Changes

- Restored `_persist_now` as a `BacklinkIndex` instance method so `_schedule_persist`, `_read_stems`, and `_rel` remain available on the class.
- Updated `check_config()` status output to ASCII `[OK]` and `[ERROR]` labels for CP1252 console compatibility.
- Cleaned ruff issues in touched files, including an unused import, long lines, import spacing, and ambiguous variable naming.

### Tests and Verification

- Added `_test_/unit/vault/test_index.py` to prove `BacklinkIndex.build()` indexes wikilink backlinks.
- Added `_test_/unit/test_main.py` to prove `check_config()` prints successfully to a CP1252 stdout stream.
- Verified focused tests pass with `.venv\Scripts\python.exe -m pytest _test_\unit\vault\test_index.py _test_\unit\test_main.py -q -p no:cacheprovider`.
- Verified `.venv\Scripts\python.exe -m obsidian_mcp check` passes against the configured vault and REST adapter.
- Verified touched files pass ruff.
- Full `_test_` collection still has pre-existing duplicate basename issues, and importlib-mode full suite has unrelated pre-existing failures.

## 2026-10-26 - Excalidraw: LLM-Safe Diagram Generation

### Investigation

- Root cause (confirmed by the user): the LLM mostly wrote raw `.excalidraw.md` JSON through `create_note`. Reading the existing generators showed they were broken too: labels were inline `text` on rectangles/arrows (ignored by Excalidraw), arrows were one-way bound or unbound, required fields were missing, and `knowledge.analysis.generate_excalidraw_markdown` emitted unlabeled boxes.
- Rendered generated diagrams to images and found a layout defect the tests missed (a long arrow crossing intermediate shapes); fixed with obstacle-avoiding curved arrows and label-aware layer gaps.

### Code Changes

- New `plugins/excalidraw_scene.py` (engine) and rewritten `plugins/excalidraw.py` (service); new tools `excalidraw_get_schema`, `_create_diagram`, `_generate_flowchart`, `_edit_diagram`, `_validate`; `parse_elements(compact=)`.
- Guard in `tools/core.py`; runtime prompt guidance in `web/app.py`; generators in `knowledge/analysis.py` routed through the engine.
- Excalidraw CLI deliberately not used (needs a running Obsidian; the failures were fixable server-side).

### Tests and Verification

- 64 new tests (engine, service, tools). LZString port verified against the real JS library. Not exercised in a running Obsidian.

### Documentation

- Added `DOCS/features/excalidraw-diagrams.md` (examples are generated by running them); updated `codebase_reference.md`, `AICONTEXT.md`, README and doc indexes.


## 2026-10-26 - Main Housekeeping (stale tests, packaging, path safety)

### Investigation

- Ran the full suite on `main`: 102 passed, 4 failed, and collection needed `--import-mode=importlib`.
- Classified each failure instead of adjusting tests blindly: three were stale expectations (relationship-graph tag edges and `read_note` backlinks are opt-in by design; `build_server()` was removed from `__main__`), one was a real bug (`Path("C:/x").is_absolute()` is False on Linux/macOS, so Windows-absolute paths were accepted as relative there).
- Found `mcp>=1.0.0` unpinned (mcp 2.x removed `mcp.server.fastmcp`), `testpaths` pointing at a non-existent `tests/`, a dead duplicate `_default_instructions()` in `server.py`, and `icon.png` referenced by `server.py`/`pyproject.toml`/`setup_wizard.py` but never committed (only `icon.ico`).
- Noted, not changed: the standalone `fastmcp` dependency is never imported; `[tool.uv] dev-dependencies` is deprecated.

### Code Changes

- `pyproject.toml`: `mcp>=1.22,<2` (1.22 is the oldest release verified with the `Icon` API under current pydantic), `testpaths=["_test_"]`, `addopts=--import-mode=importlib`; `uv.lock` refreshed (one-line diff, locked mcp stays 1.27.2).
- `vault/paths.py`: also reject absolute paths under Windows rules on every OS.
- `server.py`: removed the unreachable duplicate `_default_instructions()`; moved imports above `_load_icon()`.
- Added `src/obsidian_mcp/icon.png` as a lossless conversion of the tracked 96x96 `icon.ico` (separate commit so it can be replaced by the original).

### Tests and Verification

- Updated the three stale tests to assert the documented behaviour (both modes), parametrized the absolute-path test (drive, backslash, UNC, POSIX) and added a positive relative-path test and an icon regression test.
- `uv run pytest`: 111 passed, 0 failed, no flags.

### Documentation

- Added `DOCS/development.md`; corrected stale statements in `DOCS/AICONTEXT.md`, `DOCS/codebase_reference.md` and `DOCS/features/core-mcp-tools.md`.

