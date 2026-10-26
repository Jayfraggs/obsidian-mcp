# Development Guide

How to set up a working copy, run the tests, and what the build configuration
guarantees.

## Setup

```bash
git clone https://github.com/Jayfraggs/obsidian-mcp.git
cd obsidian-mcp
uv sync --extra dev        # installs the locked versions, including pytest/ruff/mypy
```

Use the lockfile (`uv sync`, not a bare `pip install .`): `uv.lock` pins the
versions the project is tested against.

## Running the tests

```bash
uv run pytest              # whole suite
uv run pytest _test_/unit/vault -q
uv run pytest -k backlinks
```

No extra flags are needed — `pyproject.toml` configures:

| Setting | Value | Why |
|---------|-------|-----|
| `testpaths` | `["_test_"]` | Tests live in `_test_/` (it used to point at a non-existent `tests/`). |
| `pythonpath` | `["."]` | Tests import root-level scripts (`setup_wizard.py`, `server_launcher.py`); this makes plain `pytest` work, not only `python -m pytest` (which adds the cwd to `sys.path`). |
| `addopts` | `--import-mode=importlib` | Several modules share a basename (`test_service.py`, …) and the folders have no `__init__.py`; the default import mode fails collection on that. |
| `asyncio_mode` | `auto` | `pytest-asyncio` runs `async def` tests without decorators. |

Consequences of importlib mode: test modules cannot import each other (keep
shared fixtures in the test file that uses them or in a `conftest.py`), and test
files that import `setup_wizard` mock the GUI libraries first — see
[setup-wizard.md](setup-wizard.md#testing).

### Test layout

```
_test_/
├── test_setup_wizard.py            wizard helpers (GUI mocked, headless)
├── unit/
│   ├── test_config.py / test_main.py / test_server.py
│   ├── knowledge/                  analysis + KnowledgeService
│   ├── tools/                      MCP tool registration (fake server)
│   ├── vault/                      paths, service, backlink index
│   └── web/                        FastAPI TestClient tests
```

Tests that exercise the MCP layer end to end build a real `FastMCP` server with
`create_server(...)` and call tools through `server.call_tool(...)`; prefer that
over a fake server when the behaviour under test depends on the tool signature
or schema.

## Dependency policy

- `mcp` is pinned `>=1.22,<2`. mcp 2.x removed `mcp.server.fastmcp`, so an
  unpinned install breaks at import time. 1.22 is the oldest release verified to
  work with the `Icon` API (`server.py`) under current pydantic; older ones fail
  on a pydantic internal import before that is even reached.
- After editing `pyproject.toml` dependencies run `uv lock` and commit
  `uv.lock`; `uv lock --check` should pass.
- Known cleanup candidates (not changed here): the standalone `fastmcp` package
  is listed in `dependencies` but nothing imports it (the server uses
  `mcp.server.fastmcp`), and `[tool.uv] dev-dependencies` is deprecated in favour
  of `dependency-groups.dev`.

## Behaviour that looks like a bug but is intentional

These were once flagged by stale tests; the code is deliberate and documented.

| Behaviour | Where | Reason |
|-----------|-------|--------|
| `build_relationship_graph` emits **no** shared-tag edges by default (`include_tag_edges=True` to opt in) | `knowledge/analysis.py` | Tag edges grow ~quadratically (500 notes ≈ 67k edges, 5 MB JSON). |
| `read_note` returns `backlinks: []` unless `include_backlinks=True` | `vault/service.py` | Skips the index lookup for the common case. |
| `create_server` has no `build_server()` wrapper | `server.py`, `__main__.py` | Startup is `_build_vault_service()` (or `_load_runtime()` with several vaults) → `create_server(...)`. |

## Path safety contract

`VaultPathResolver.resolve_relative_path` rejects **absolute paths of any
flavour on every OS**: POSIX (`/etc/passwd`), Windows drive (`C:/x`, `C:\x`) and
UNC (`\\server\share`). `Path("C:/x").is_absolute()` is `False` on Linux and
macOS, so the resolver also applies Windows rules; otherwise a vault synced
between machines would accept on one OS what it rejects on another. Traversal
(`..`) and anything resolving outside the vault are rejected as before.

## Bundled assets

`src/obsidian_mcp/icon.png` (96×96 RGBA) is loaded by `server.py` (MCP server
icon), by `setup_wizard.py` (window icon) and shipped in the wheel (see
`[tool.hatch.build.targets.wheel] artifacts`). `_load_icon()` deliberately
swallows errors, so a missing file produces **no** icon rather than a crash —
`test_bundled_icon_exists_and_loads` guards against that regressing silently.
`icon.ico` (used for the Windows shortcut) is the same artwork.
