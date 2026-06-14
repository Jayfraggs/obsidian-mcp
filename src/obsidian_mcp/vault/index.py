"""Inverted backlink index with watchdog-powered incremental updates
and disk-persisted cold-start cache.

Architecture
------------
BacklinkIndex maintains two complementary dicts:

    _forward:  path  → set of stems this note links TO
    _reverse:  stem  → set of paths that link to this stem   ← the index

Cold-start persistence
----------------------
On ``build()``, if ``.obsidian/mcp-index.json`` exists and is valid:
  1. Load forward/reverse from the JSON.
  2. Find all .md files whose mtime > index ``saved_at`` timestamp.
  3. Re-index only those files (incremental diff).
  4. Save the updated index back to disk.

If the cache is absent, malformed, or from a different vault, fall back
to a full scan and save afterward.

The JSON layout is:

    {
      "version": 1,
      "vault": "/absolute/path/to/vault",
      "saved_at": 1718000000.0,
      "forward": {"rel/path.md": ["stem1", "stem2"], ...}
    }

``reverse`` is not stored — it is trivially reconstructed from ``forward``
in O(N) which is fast enough and avoids double-storing data.

Watchdog
--------
After ``build()`` the watchdog Observer runs in a daemon thread patching
only the affected entries on each filesystem event — O(1) per event.
Every mutation also calls ``_persist()`` to keep the sidecar current.

Thread safety
-------------
All mutations go through ``threading.Lock``.

Lifecycle
---------
    index = BacklinkIndex(vault_path)
    index.build()      # load/diff/full-scan + save
    index.start()      # starts watchdog observer thread
    ...
    index.stop()       # clean shutdown
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any

from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEventHandler,
)
from watchdog.observers import Observer

from obsidian_mcp.adapters.filesystem import _is_excluded

logger = logging.getLogger("obsidian_mcp.vault.index")

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")
_INDEX_VERSION = 1
_INDEX_FILENAME = ".obsidian/mcp-index.json"


def _extract_link_stems(content: str) -> set[str]:
    """Return the lowercased stems of every wikilink in *content*."""
    stems: set[str] = set()
    for m in _WIKILINK_RE.finditer(content):
        raw = m.group(1).strip()
        stems.add(Path(raw).stem.lower())
    return stems


class BacklinkIndex:
    """In-process inverted index: stem → set[source_path].

    All public methods are thread-safe.
    """

    def __init__(self, vault_path: Path) -> None:
        self._vault = vault_path.resolve()
        self._cache_path = self._vault / _INDEX_FILENAME
        self._lock = threading.Lock()
        # forward[path] = set of stems that *path* links to
        self._forward: dict[str, set[str]] = {}
        # reverse[stem] = set of paths that link to *stem*
        self._reverse: dict[str, set[str]] = {}
        self._observer: Observer | None = None
        self._built = False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def build(self) -> None:
        """Populate the index at startup, using the on-disk cache when possible.

        Strategy:
          1. Try to load the persisted index.
          2. If valid: diff against current mtimes, re-index only changed files.
          3. If invalid/absent: full scan.
          4. Persist the result.
        """
        loaded_at, forward = self._load_cache()

        if loaded_at is not None and forward is not None:
            self._build_incremental(forward, loaded_at)
        else:
            self._build_full()

        self._persist()

    def start(self) -> None:
        """Start the watchdog observer thread for incremental updates."""
        if self._observer is not None:
            return
        handler = _VaultEventHandler(self)
        observer = Observer()
        observer.schedule(handler, str(self._vault), recursive=True)
        observer.daemon = True
        observer.start()
        self._observer = observer
        logger.info("BacklinkIndex: watchdog observer started")

    def stop(self) -> None:
        """Stop the watchdog observer thread and persist final state."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("BacklinkIndex: watchdog observer stopped")
        # Save on clean shutdown so the next cold start is as fresh as possible
        self._persist()

    def find(self, target_path: str) -> list[str]:
        """Return sorted list of paths that link to *target_path*'s stem.

        O(1) dict lookup after build().
        """
        stem = Path(target_path).stem.lower()
        with self._lock:
            return sorted(self._reverse.get(stem, set()))

    def is_ready(self) -> bool:
        """True once build() has completed."""
        return self._built

    # ------------------------------------------------------------------ #
    # Build strategies
    # ------------------------------------------------------------------ #

    def _build_full(self) -> None:
        """Scan every .md file in the vault from scratch."""
        logger.info("BacklinkIndex: full scan starting (no valid cache)")
        forward: dict[str, set[str]] = {}
        reverse: dict[str, set[str]] = {}
        count = 0

        for md_path in self._vault.rglob("*.md"):
            if not md_path.is_file() or _is_excluded(md_path, self._vault):
                continue
            rel = self._rel(md_path)
            stems = self._read_stems(md_path)
            if stems is None:
                continue
            forward[rel] = stems
            for stem in stems:
                reverse.setdefault(stem, set()).add(rel)
            count += 1

        with self._lock:
            self._forward = forward
            self._reverse = reverse
            self._built = True

        logger.info("BacklinkIndex: full scan done — %d notes, %d link targets", count, len(reverse))

    def _build_incremental(
        self,
        loaded_forward: dict[str, set[str]],
        loaded_at: float,
    ) -> None:
        """Start from cached forward map and re-index only files newer than *loaded_at*."""
        # Reconstruct reverse from loaded forward — O(N), cheap
        reverse: dict[str, set[str]] = {}
        for path, stems in loaded_forward.items():
            for stem in stems:
                reverse.setdefault(stem, set()).add(path)

        stale: list[Path] = []
        deleted: list[str] = []

        # Find files that changed since the cache was saved
        current_rels: set[str] = set()
        for md_path in self._vault.rglob("*.md"):
            if not md_path.is_file() or _is_excluded(md_path, self._vault):
                continue
            rel = self._rel(md_path)
            current_rels.add(rel)
            try:
                mtime = md_path.stat().st_mtime
            except OSError:
                continue
            if mtime > loaded_at:
                stale.append(md_path)

        # Files that were in the cache but no longer exist
        for rel in loaded_forward:
            if rel not in current_rels:
                deleted.append(rel)

        logger.info(
            "BacklinkIndex: incremental load — cache had %d notes, %d stale, %d deleted",
            len(loaded_forward),
            len(stale),
            len(deleted),
        )

        # Apply deletes
        for rel in deleted:
            old_stems = loaded_forward.pop(rel, set())
            for stem in old_stems:
                reverse.get(stem, set()).discard(rel)
                if not reverse.get(stem):
                    reverse.pop(stem, None)

        # Re-index stale files
        for md_path in stale:
            rel = self._rel(md_path)
            # Remove old entries for this file
            old_stems = loaded_forward.pop(rel, set())
            for stem in old_stems:
                reverse.get(stem, set()).discard(rel)
                if not reverse.get(stem):
                    reverse.pop(stem, None)
            # Add new entries
            new_stems = self._read_stems(md_path)
            if new_stems is not None:
                loaded_forward[rel] = new_stems
                for stem in new_stems:
                    reverse.setdefault(stem, set()).add(rel)

        with self._lock:
            self._forward = loaded_forward
            self._reverse = reverse
            self._built = True

        logger.info("BacklinkIndex: incremental build complete — %d notes", len(loaded_forward))

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def _load_cache(self) -> tuple[float | None, dict[str, set[str]] | None]:
        """Try to load the on-disk cache.

        Returns (saved_at, forward) on success, (None, None) on any failure.
        Never raises.
        """
        if not self._cache_path.exists():
            logger.debug("BacklinkIndex: no cache file found at %s", self._cache_path)
            return None, None

        try:
            raw: dict[str, Any] = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("BacklinkIndex: cache unreadable (%s), will full-scan", exc)
            return None, None

        # Validate
        if raw.get("version") != _INDEX_VERSION:
            logger.warning("BacklinkIndex: cache version mismatch, will full-scan")
            return None, None
        if raw.get("vault") != str(self._vault):
            logger.warning("BacklinkIndex: cache is for a different vault, will full-scan")
            return None, None

        saved_at: float | None = raw.get("saved_at")
        raw_forward: dict | None = raw.get("forward")

        if not isinstance(saved_at, (int, float)) or not isinstance(raw_forward, dict):
            logger.warning("BacklinkIndex: cache schema invalid, will full-scan")
            return None, None

        # Deserialise lists → sets
        forward: dict[str, set[str]] = {
            path: set(stems) for path, stems in raw_forward.items()
        }

        logger.info(
            "BacklinkIndex: loaded cache (%d notes, saved %.0fs ago)",
            len(forward),
            time.time() - saved_at,
        )
        return float(saved_at), forward

    def _persist(self) -> None:
        """Serialise the current forward map to the sidecar JSON file.

        Writes atomically via a temp file to avoid partial writes.
        Never raises — failures are logged and swallowed.
        """
        try:
            # Ensure .obsidian/ exists (it always should, but be safe)
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)

            with self._lock:
                forward_snapshot = {
                    path: sorted(stems)          # set → sorted list for stable JSON
                    for path, stems in self._forward.items()
                }

            payload = {
                "version": _INDEX_VERSION,
                "vault": str(self._vault),
                "saved_at": time.time(),
                "forward": forward_snapshot,
            }

            # Atomic write: write to .tmp then rename
            tmp = self._cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=None, separators=(",", ":")), encoding="utf-8")
            tmp.replace(self._cache_path)

            logger.debug("BacklinkIndex: persisted %d entries to %s", len(forward_snapshot), self._cache_path)

        except Exception as exc:  # noqa: BLE001
            logger.warning("BacklinkIndex: failed to persist cache: %s", exc)

    # ------------------------------------------------------------------ #
    # Internal: incremental update helpers (called from watchdog + service)
    # ------------------------------------------------------------------ #

    def _remove_file(self, rel: str) -> None:
        """Remove *rel* from the index entirely."""
        with self._lock:
            old_stems = self._forward.pop(rel, set())
            for stem in old_stems:
                self._reverse.get(stem, set()).discard(rel)
                if not self._reverse.get(stem):
                    self._reverse.pop(stem, None)
        self._persist()

    def _add_file(self, abs_path: Path) -> None:
        """Index *abs_path*, adding it to forward and reverse maps."""
        if _is_excluded(abs_path, self._vault):
            return
        rel = self._rel(abs_path)
        stems = self._read_stems(abs_path)
        if stems is None:
            return
        with self._lock:
            self._forward[rel] = stems
            for stem in stems:
                self._reverse.setdefault(stem, set()).add(rel)
        self._persist()

    def _update_file(self, abs_path: Path) -> None:
        """Re-index *abs_path* (remove old entries, add new)."""
        if _is_excluded(abs_path, self._vault):
            return
        rel = self._rel(abs_path)
        stems = self._read_stems(abs_path)

        with self._lock:
            # Remove stale entries
            old_stems = self._forward.pop(rel, set())
            for stem in old_stems:
                self._reverse.get(stem, set()).discard(rel)
                if not self._reverse.get(stem):
                    self._reverse.pop(stem, None)
            # Add new entries (if file still readable)
            if stems is not None:
                self._forward[rel] = stems
                for stem in stems:
                    self._reverse.setdefault(stem, set()).add(rel)

        self._persist()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _read_stems(self, abs_path: Path) -> set[str] | None:
        """Read *abs_path* and return its wikilink stems. None on OSError."""
        try:
            content = abs_path.read_text(encoding="utf-8", errors="ignore")
            return _extract_link_stems(content)
        except OSError:
            return None

    def _rel(self, abs_path: Path) -> str:
        """Vault-relative posix path string."""
        try:
            return abs_path.relative_to(self._vault).as_posix()
        except ValueError:
            return abs_path.as_posix()


class _VaultEventHandler(FileSystemEventHandler):
    """Watchdog handler that patches BacklinkIndex on .md file events."""

    def __init__(self, index: BacklinkIndex) -> None:
        super().__init__()
        self._index = index

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        logger.debug("BacklinkIndex: created %s", event.src_path)
        self._index._add_file(Path(event.src_path))

    def on_deleted(self, event: FileDeletedEvent) -> None:
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        rel = self._index._rel(Path(event.src_path))
        logger.debug("BacklinkIndex: deleted %s", rel)
        self._index._remove_file(rel)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        logger.debug("BacklinkIndex: modified %s", event.src_path)
        self._index._update_file(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        if event.src_path.endswith(".md"):
            src_rel = self._index._rel(Path(event.src_path))
            logger.debug("BacklinkIndex: moved (src) %s", src_rel)
            self._index._remove_file(src_rel)
        if event.dest_path.endswith(".md"):
            logger.debug("BacklinkIndex: moved (dst) %s", event.dest_path)
            self._index._add_file(Path(event.dest_path))
