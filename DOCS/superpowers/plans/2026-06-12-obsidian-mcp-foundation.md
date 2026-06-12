# Obsidian MCP Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Prompt 1 foundation for a production-grade Python 3.11+ Obsidian MCP server.

**Architecture:** Use a `src/obsidian_mcp` package with focused modules for configuration, logging, errors, server creation, and CLI startup. Tests live under `_test_` and drive each production module before implementation. Prompt 2 tools will later register through the server factory without rewriting the foundation.

**Tech Stack:** Python 3.11+, MCP SDK, Pydantic Settings, pytest, watchdog, rapidfuzz, python-frontmatter, PyYAML.

---

## File Structure

- Create: `pyproject.toml` for package metadata, runtime dependencies, test config, and strict tooling defaults.
- Create: `README.md` for setup and usage.
- Create: `.gitignore` for Python and environment artifacts.
- Create: `src/obsidian_mcp/__init__.py` for package exports.
- Create: `src/obsidian_mcp/config.py` for validated settings.
- Create: `src/obsidian_mcp/errors.py` for structured application errors.
- Create: `src/obsidian_mcp/logging.py` for centralized logging setup.
- Create: `src/obsidian_mcp/server.py` for MCP server creation and future registration hooks.
- Create: `src/obsidian_mcp/__main__.py` for CLI execution.
- Create: `_test_/unit/test_config.py` for settings behavior.
- Create: `_test_/unit/test_errors.py` for safe error payloads.
- Create: `_test_/unit/test_logging.py` for logger setup behavior.
- Create: `_test_/unit/test_server.py` for server factory behavior.
- Modify: `DOCS/AICONTEXT.md` after implementation.
- Modify: `DOCS/codebase_reference.md` after new functions/classes are created.
- Modify: `DOCS/features/environment-and-architecture.md` after implementation.
- Modify: `agent_logs.md` throughout major steps.

### Task 1: Packaging And Test Harness

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `src/obsidian_mcp/__init__.py`
- Create: `_test_/unit/test_config.py`

- [ ] **Step 1: Write the initial failing import test**

```python
from obsidian_mcp.config import ObsidianMCPSettings


def test_settings_model_can_be_imported() -> None:
    assert ObsidianMCPSettings.__name__ == "ObsidianMCPSettings"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest _test_/unit/test_config.py::test_settings_model_can_be_imported -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'obsidian_mcp'`.

- [ ] **Step 3: Create package metadata and minimal package**

Create `pyproject.toml` with package metadata, dependencies, pytest path config, and strict Python version. Create `src/obsidian_mcp/__init__.py` and a minimal `src/obsidian_mcp/config.py` containing an empty `ObsidianMCPSettings` class only.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest _test_/unit/test_config.py::test_settings_model_can_be_imported -v`

Expected: PASS.

### Task 2: Configuration Foundation

**Files:**
- Modify: `src/obsidian_mcp/config.py`
- Modify: `_test_/unit/test_config.py`

- [ ] **Step 1: Add failing tests for defaults, environment loading, and path validation**

```python
from pathlib import Path

import pytest
from pydantic import ValidationError

from obsidian_mcp.config import LogLevel, ObsidianMCPSettings, load_settings


def test_settings_use_safe_defaults(tmp_path: Path) -> None:
    settings = ObsidianMCPSettings(vault_path=tmp_path)

    assert settings.vault_path == tmp_path
    assert settings.server_name == "obsidian-mcp"
    assert settings.log_level is LogLevel.INFO


def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OBSIDIAN_MCP_VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("OBSIDIAN_MCP_SERVER_NAME", "notes-server")
    monkeypatch.setenv("OBSIDIAN_MCP_LOG_LEVEL", "DEBUG")

    settings = load_settings()

    assert settings.vault_path == tmp_path
    assert settings.server_name == "notes-server"
    assert settings.log_level is LogLevel.DEBUG


def test_settings_reject_missing_vault_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing"

    with pytest.raises(ValidationError):
        ObsidianMCPSettings(vault_path=missing_path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest _test_/unit/test_config.py -v`

Expected: FAIL because `LogLevel`, validation, and `load_settings` are not fully implemented.

- [ ] **Step 3: Implement configuration**

Implement `LogLevel`, `ObsidianMCPSettings`, and `load_settings` using Pydantic Settings. Validate that `vault_path` exists and is a directory.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest _test_/unit/test_config.py -v`

Expected: PASS.

### Task 3: Error Foundation

**Files:**
- Create: `src/obsidian_mcp/errors.py`
- Create: `_test_/unit/test_errors.py`

- [ ] **Step 1: Write failing tests for safe error payloads**

```python
from obsidian_mcp.errors import ApplicationError, ConfigurationError, ErrorCode


def test_application_error_exposes_safe_payload() -> None:
    error = ApplicationError(
        code=ErrorCode.CONFIGURATION_INVALID,
        message="Configuration is invalid.",
        internal_detail="secret path detail",
    )

    assert error.to_public_dict() == {
        "code": "configuration_invalid",
        "message": "Configuration is invalid.",
    }


def test_configuration_error_has_stable_code() -> None:
    error = ConfigurationError("Missing vault path.")

    assert error.code is ErrorCode.CONFIGURATION_INVALID
    assert str(error) == "Missing vault path."
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest _test_/unit/test_errors.py -v`

Expected: FAIL because `obsidian_mcp.errors` does not exist.

- [ ] **Step 3: Implement structured errors**

Implement `ErrorCode`, `ApplicationError`, and `ConfigurationError`. Keep internal details available only on the exception object, not public payloads.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest _test_/unit/test_errors.py -v`

Expected: PASS.

### Task 4: Logging Foundation

**Files:**
- Create: `src/obsidian_mcp/logging.py`
- Create: `_test_/unit/test_logging.py`

- [ ] **Step 1: Write failing tests for centralized logging setup**

```python
import logging

from obsidian_mcp.config import LogLevel
from obsidian_mcp.logging import configure_logging, get_logger


def test_configure_logging_sets_package_logger_level() -> None:
    logger = configure_logging(LogLevel.DEBUG)

    assert logger.name == "obsidian_mcp"
    assert logger.level == logging.DEBUG
    assert logger.propagate is False


def test_get_logger_returns_child_logger() -> None:
    logger = get_logger("server")

    assert logger.name == "obsidian_mcp.server"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest _test_/unit/test_logging.py -v`

Expected: FAIL because `obsidian_mcp.logging` does not exist.

- [ ] **Step 3: Implement logging helpers**

Implement idempotent `configure_logging` and `get_logger` helpers with a stream handler and deterministic formatter.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest _test_/unit/test_logging.py -v`

Expected: PASS.

### Task 5: MCP Server Factory

**Files:**
- Create: `src/obsidian_mcp/server.py`
- Create: `_test_/unit/test_server.py`

- [ ] **Step 1: Write failing tests for server creation**

```python
from pathlib import Path

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.server import create_server


def test_create_server_uses_configured_name(tmp_path: Path) -> None:
    settings = ObsidianMCPSettings(vault_path=tmp_path, server_name="test-server")

    server = create_server(settings)

    assert getattr(server, "name") == "test-server"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest _test_/unit/test_server.py -v`

Expected: FAIL because `obsidian_mcp.server` does not exist.

- [ ] **Step 3: Implement server factory**

Implement `create_server(settings: ObsidianMCPSettings) -> FastMCP` using `mcp.server.fastmcp.FastMCP`. Keep a private registration helper for future Prompt 2 tools.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest _test_/unit/test_server.py -v`

Expected: PASS.

### Task 6: CLI Entry Point And Documentation

**Files:**
- Create: `src/obsidian_mcp/__main__.py`
- Create: `README.md`
- Modify: `DOCS/AICONTEXT.md`
- Modify: `DOCS/codebase_reference.md`
- Modify: `DOCS/features/environment-and-architecture.md`
- Modify: `agent_logs.md`

- [ ] **Step 1: Write failing import-level CLI test**

Add to `_test_/unit/test_server.py`:

```python
from obsidian_mcp.__main__ import build_server


def test_build_server_returns_configured_server(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OBSIDIAN_MCP_VAULT_PATH", str(tmp_path))

    server = build_server()

    assert getattr(server, "name") == "obsidian-mcp"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest _test_/unit/test_server.py::test_build_server_returns_configured_server -v`

Expected: FAIL because `obsidian_mcp.__main__` does not exist.

- [ ] **Step 3: Implement CLI startup helper**

Implement `build_server()` and `main()` in `__main__.py`. `build_server()` loads settings, configures logging, and creates the server. `main()` calls `server.run()`.

- [ ] **Step 4: Run all tests**

Run: `python -m pytest -v`

Expected: PASS.

- [ ] **Step 5: Update documentation**

Update README setup instructions, function registry, feature documentation, AI context, and action log with the implemented foundation.

### Task 7: Final Verification

**Files:**
- No new production files.

- [ ] **Step 1: Run the complete test suite**

Run: `python -m pytest -v`

Expected: PASS.

- [ ] **Step 2: Run import smoke test**

Run: `python -c "from obsidian_mcp.__main__ import build_server; print(build_server)"`

Expected: command exits successfully and prints a function representation.

- [ ] **Step 3: Confirm docs are current**

Review `DOCS/AICONTEXT.md`, `DOCS/codebase_reference.md`, `DOCS/features/environment-and-architecture.md`, and `agent_logs.md`.

Expected: documents mention implemented foundation modules and no stale "not implemented" statements remain.

## Self-Review

- Spec coverage: Prompt 1 requirements are covered by packaging, config, logging, errors, tests, modular architecture, type hints, and documentation tasks.
- Placeholder scan: No `TBD`, `TODO`, or unbounded "implement later" instructions are present.
- Type consistency: Planned names are consistent across tasks: `ObsidianMCPSettings`, `LogLevel`, `load_settings`, `ApplicationError`, `ConfigurationError`, `ErrorCode`, `configure_logging`, `get_logger`, `create_server`, and `build_server`.
