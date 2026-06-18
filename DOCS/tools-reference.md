# MCP Tools Reference

This document lists MCP tools provided by the Obsidian MCP server and
notes about their behaviour and safety.

## delete_folder

- **Name:** `delete_folder`
- **Description:** Delete a vault folder. This operation is destructive.
- **Parameters:**
  - `path: str` — Vault-relative folder path (e.g. `Projects/Old`)
  - `recursive: bool` — When `False` (default) the folder must be empty.
  - `confirm: bool` — Must be `True` to actually perform deletion.
- **Returns:** `{"path": "<vault_rel>", "deleted": True}` on success.

### Safety

- The server refuses to delete the vault root directory.
- The delete operation requires `confirm=True` to proceed.
- Permission profiles may prevent deletes entirely (see `Permission profiles`).
- For filesystem-backed adapters the directory tree is removed via
  `shutil.rmtree` after files are deleted through the adapter.

### Example

```
delete_folder("Projects/Old", recursive=True, confirm=True)
```
