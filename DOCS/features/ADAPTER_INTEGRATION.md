# Adapter Integration — Change Summary

## What changed

### New: `obsidian_mcp/adapters/`
| File | Purpose |
|---|---|
| `base.py` | `ObsidianAdapter` ABC + `RawNote` / `RawSearchResult` dataclasses |
| `filesystem.py` | Direct pathlib I/O — identical behaviour to the original `VaultService` |
| `rest_api.py` | HTTP client for the Obsidian Local REST API plugin |
| `auto.py` | Probes REST at startup, falls back to filesystem silently |
| `__init__.py` | Public surface: `AutoAdapter`, `ObsidianAdapter`, etc. |

### Modified: `config.py`
Three new fields (all optional, backward-compatible):
- `OBSIDIAN_MCP_ADAPTER_MODE` — `auto` | `rest` | `filesystem`
- `OBSIDIAN_MCP_ADAPTER_API_KEY` — REST API plugin key
- `OBSIDIAN_MCP_ADAPTER_HOST` / `OBSIDIAN_MCP_ADAPTER_PORT`

### Modified: `vault/service.py`
`VaultService.__init__` now accepts an optional `adapter: ObsidianAdapter`.
All raw file I/O is delegated to it.  When `adapter=None`, a
`FilesystemAdapter` is constructed automatically — **zero behaviour change**
for any caller that passes only `vault_path`.

### Modified: `server.py`, `tools/core.py`, `tools/knowledge.py`, `web/app.py`
Each now accepts an optional `vault_service: VaultService` kwarg.
When `None`, they construct a default filesystem-backed service as before.

### Modified: `__main__.py`
Single construction site: `AutoAdapter.from_settings(settings)` is called
once at startup, passed to `VaultService`, and that service flows through
to all tools and the web app.

## Nothing that didn't change
- `errors.py`, `permissions.py`, `logging.py`, `__init__.py`
- `vault/paths.py`, `vault/metadata.py`
- `knowledge/analysis.py`, `knowledge/service.py`
- `web/static/` (all frontend assets)
- Every tool name, signature, and return shape
