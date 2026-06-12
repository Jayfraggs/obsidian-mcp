# Obsidian MCP

Production-grade Python MCP server foundation for Obsidian vault workflows.

## Status

This project has the Prompt 1 foundation stage implemented. It currently includes environment setup, configuration, logging, error handling, tests, modular architecture, type hints, and docstrings.

Prompt 2 note tools and Prompt 3 advanced features will be layered on top of this foundation.

## Development

Use `uv` to create the Python environment and run tests:

```powershell
uv run --extra dev pytest -v
```

The server expects an Obsidian vault path through `OBSIDIAN_MCP_VAULT_PATH` once configuration loading is implemented.

```powershell
$env:OBSIDIAN_MCP_VAULT_PATH = "C:\path\to\vault"
uv run obsidian-mcp
```
