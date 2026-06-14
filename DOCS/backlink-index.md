# Backlink Index

Technical reference for the `BacklinkIndex` system introduced in June 2026.

---

## Why it exists

The original `find_backlinks()` implementation read every `.md` file in the vault
on every single call — O(N) disk reads per lookup. On a vault of any meaningful
size this caused MCP tool timeouts (observed: 4+ minute hangs for `read_note` on
a ~200 note vault). The index eliminates that cost entirely.

---

## Architecture

`BacklinkIndex` (`vault/index.py`) maintains two in-memory dicts under a
`threading.Lock`:

```
_forward  :  path → set[stems]    # what each note links TO
_reverse  :  stem → set[paths]    # the actual index: what links to this stem
```

`find(target_path)` is a pure dict lookup against `_reverse` — O(1) regardless
of vault size.

### Startup sequence

```
VaultService.__init__()
    └── BacklinkIndex.__init__()       # allocates dicts, no I/O

VaultService.start()                   # called from __main__.py
    ├── BacklinkIndex.build()          # populate index (see below)
    └── BacklinkIndex.start()          # spin up watchdog observer thread
```

### Shutdown sequence

```
VaultService.stop()                    # called in try/finally in __main__.py
    └── BacklinkIndex.stop()
        ├── observer.stop() + join()
        └── _persist()                 # write final state to disk
```

---

## Cold-start persistence

The index is persisted to `.obsidian/mcp-index.json` so that restarts — common
with Claude Desktop, which kills the MCP process when idle — don't require a
full vault scan each time.

### Build strategy

On `build()`, the following logic runs:

```
cache exists and valid?
├── YES → incremental build
│         1. Load forward map from JSON
│         2. Reconstruct reverse from forward  (O(N), no disk reads)
│         3. rglob for *.md files with mtime > saved_at
│         4. Re-index only those files
│         5. Drop entries for files that no longer exist
│         6. _persist() updated index
└── NO  → full scan
          1. rglob all *.md, read each, extract wikilinks
          2. Build forward + reverse from scratch
          3. _persist() result
```

The cache is considered invalid if:

- The file doesn't exist yet (first run)
- JSON is malformed or unreadable
- `version` field doesn't match `_INDEX_VERSION = 1`
- `vault` field doesn't match the current vault path (e.g. vault was moved)

In all invalid cases the code falls through to a full scan with a `WARNING` log
entry explaining why.

### Cache file format

```json
{
  "version": 1,
  "vault": "/absolute/path/to/vault",
  "saved_at": 1718000000.0,
  "forward": {
    "HomeLab_Knowledge_Base/vault/24 AI Systems/24.01 DeepSeek V4 Infrastructure.md": [
      "deepseek r2",
      "gpu cluster"
    ],
    "HomeLab_Knowledge_Base/vault/Templates/TPL Service.md": [
      "runbook template"
    ]
  }
}
```

`reverse` is not stored — it is trivially reconstructed from `forward` in O(N)
at load time. Storing it would double the file size for no benefit.

The file is written atomically: content goes to `.obsidian/mcp-index.tmp`, then
`tmp.replace(cache_path)`. This prevents a partial write from corrupting the
cache on a crash or SIGKILL.

---

## Live updates (watchdog)

After `build()`, a `watchdog.observers.Observer` thread watches the entire vault
directory recursively. The `_VaultEventHandler` handles four events:

| Event | Action |
|-------|--------|
| `FileCreatedEvent` (`.md`) | `_add_file(path)` |
| `FileDeletedEvent` (`.md`) | `_remove_file(rel)` |
| `FileModifiedEvent` (`.md`) | `_update_file(path)` — remove old, add new |
| `FileMovedEvent` | `_remove_file(src)` + `_add_file(dst)` if `.md` |

All events that involve excluded directories (`.git`, `.obsidian`, `copilot`,
etc.) are silently dropped by the `_is_excluded()` check inside each handler.

Each mutation helper (`_add_file`, `_remove_file`, `_update_file`) also calls
`_persist()` to keep the sidecar current throughout the session.

### Eager mutation hooks

`VaultService` also calls the index mutation helpers directly on every write
operation (`create_note`, `update_note`, `append_note`, `delete_note`,
`move_note`, `rename_note`). This closes the small window (~100 ms) between
a write completing and the watchdog event firing, so a `find_backlinks` call
immediately after a write never sees stale data.

---

## Thread safety

All mutations to `_forward` and `_reverse` are guarded by a single
`threading.Lock`. The watchdog observer and MCP handler threads may both
call mutation helpers concurrently — the lock ensures they never see a
torn index state.

`find()` also acquires the lock for the duration of the `_reverse` lookup
and `set` copy, then releases it before sorting. This means `find()` is
safe to call from any thread at any time after `build()`.

---

## Fallback behaviour

If `find_backlinks()` is called before `start()` has completed (e.g. in unit
tests that bypass the full lifecycle), `is_ready()` returns `False` and
`VaultService` falls back to `_find_backlinks_linear()` — the original O(N)
per-call scan. A `WARNING` log entry is emitted. This should never happen in
production.

---

## Performance characteristics

| Operation | Complexity | Notes |
|-----------|-----------|-------|
| Cold start (no cache) | O(N) reads | One-time at startup |
| Cold start (cache hit, 0 stale files) | O(N) CPU | No disk reads beyond cache file |
| Cold start (cache hit, K stale files) | O(K) reads | Only changed files re-read |
| `find_backlinks()` | O(1) | Dict lookup + set copy + sort |
| `suggest_backlinks()` in `KnowledgeService` | O(N) | Full `_documents()` scan — inherent to semantic ranking |
| Watchdog event (create/modify/delete) | O(L) | L = wikilinks in the affected file |
| `_persist()` | O(N) | Serialises entire forward map; called after each mutation |

`_persist()` is the main cost of live updates. On a vault with thousands of
notes this could become noticeable if notes are being written in rapid bursts
(e.g. bulk import). If that becomes an issue, debouncing `_persist()` with a
short delay (e.g. 2 s after last write) is a straightforward improvement.

---

## Excluded directories

The index respects the same exclusion list as `FilesystemAdapter`:

```python
_EXCLUDED_DIR_NAMES = {".git", ".obsidian", "copilot", ".trash", "node_modules"}
```

Any path component matching this set, or starting with `.`, is skipped during
both the initial scan and watchdog event handling.

---

## Files changed

| File | Change |
|------|--------|
| `src/obsidian_mcp/vault/index.py` | New file — `BacklinkIndex` + `_VaultEventHandler` |
| `src/obsidian_mcp/vault/service.py` | Wires in `BacklinkIndex`; adds `start()`/`stop()` lifecycle; eager index mutation hooks on all writes; `find_backlinks()` delegates to index |
| `src/obsidian_mcp/__main__.py` | Calls `vault_service.start()` before `server.run()` and `vault_service.stop()` in `finally` block, in both `main()` and `web_main()` |
| `src/obsidian_mcp/adapters/filesystem.py` | `_EXCLUDED_DIR_NAMES` and `_is_excluded()` moved here (shared with index) |
| `src/obsidian_mcp/knowledge/service.py` | `_documents()` reads via `_adapter` directly, bypassing `find_backlinks`; all `read_note()` calls pass `include_backlinks=False` |

---

## Logging reference

All index log entries use the logger `obsidian_mcp.vault.index`. Set
`OBSIDIAN_MCP_LOG_LEVEL=DEBUG` in `.env` to see per-file watchdog events.

| Level | Message | When |
|-------|---------|------|
| `INFO` | `BacklinkIndex: building index for <path>` | Full scan start |
| `INFO` | `BacklinkIndex: full scan done — N notes, M link targets` | Full scan complete |
| `INFO` | `BacklinkIndex: loaded cache (N notes, saved Xs ago)` | Cache loaded successfully |
| `INFO` | `BacklinkIndex: incremental load — cache had N notes, K stale, D deleted` | Incremental build start |
| `INFO` | `BacklinkIndex: incremental build complete — N notes` | Incremental build done |
| `INFO` | `BacklinkIndex: watchdog observer started` | Observer thread up |
| `INFO` | `BacklinkIndex: watchdog observer stopped` | Observer thread down |
| `WARNING` | `BacklinkIndex: cache unreadable (...)` | JSON parse failure |
| `WARNING` | `BacklinkIndex: cache version mismatch` | Schema version changed |
| `WARNING` | `BacklinkIndex: cache is for a different vault` | Vault path mismatch |
| `WARNING` | `BacklinkIndex: cache schema invalid` | Missing/wrong-typed fields |
| `WARNING` | `BacklinkIndex: failed to persist cache: ...` | Write error (swallowed) |
| `WARNING` | `find_backlinks called before index is ready` | Called before `start()` |
| `DEBUG` | `BacklinkIndex: created/modified/deleted/moved <path>` | Watchdog events |
| `DEBUG` | `BacklinkIndex: persisted N entries to <path>` | After each `_persist()` |
