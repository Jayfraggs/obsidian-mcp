"""Inverted backlink index with watchdog-powered incremental updates
and disk-persisted cold-start cache.

Architecture
------------
BacklinkIndex maintains two complementary dicts:

    _forward:  path  → set of stems this note links TO
    _reverse:  stem  → set of paths that link to this stem   ← the index

Cold-start persistence
----------------------
On ``build()``, if the cache file exists and is valid:
  1. Load forward/reverse from the JSON.
  2. Find all .md files whose mtime > index ``saved_at`` timestamp.
  3. Re-index only those files (incremental diff).
  4. Save the updated index back to disk.

Cache location
--------------
The cache is written to the system temp directory by default
(``tempfile.gettempdir() / "obsidian-mcp" / <vault_slug>.json``)
rather than inside ``.obsidian/``. This avoids conflicts with
OneDrive / Dropbox / remotely-save sync clients which hold file locks
on everything inside the vault directory.

Debounced persistence
---------------------
``_persist()`` is NOT called immediately on every watchdog event.
Instead, mutations set a ``_dirty`` flag and schedule a background
timer (``_PERSIST_DEBOUNCE_S = 2.0`` seconds). The timer fires once
after the burst of events settles, then writes once. Explicit calls
from ``build()`` and ``stop()`` bypass the debounce and write immediately.

Thread safety
-------------
All mutations go through ``threading.Lock``.

Lifecycle
---------
    index = BacklinkIndex(vault_path)
    index.build()      # load/diff/full-scan + immediate persist
    index.start()      # starts watchdog observer thread
    ...
    index.stop()       # stops watcher + immediate persist
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
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
_PERSIST_DEBOUNCE_S = 2.0  # seconds to wait after last mutation before writing


def _cache_path_for_vault(vault_path: Path) -> Path:
    """Return a stable temp-dir path for this vault's cache file.

    Uses a short hash of the absolute vault path so two different vaults
    never collide, and the filename is human-readable enough to identify.

        <tempdir>/obsidian-mcp/<slug>-<hash8>.json

    This deliberately avoids writing inside the vault directory to prevent
    conflicts with OneDrive / Dropbox / remotely-save sync locks.
    """
    resolved = str(vault_path.resolve())
    slug = vault_path.resolve().name.lower().replace(" ", "-")[:32]
    hash8 = hashlib.sha1(resolved.encode()).hexdigest()[:8]
    cache_dir = Path(tempfile.gettempdir()) / "obsidian-mcp"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{slug}-{hash8}.json"


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
        self._cache_path = _cache_path_for_vault(vault_path)
        self._lock = threading.Lock()
        # forward[path] = set of stems that *path* links to
        self._forward: dict[str, set[str]] = {}
        # reverse[stem] = set of paths that link to *stem*
        self._reverse: dict[str, set[str]] = {}
        self._observer: Observer | None = None
        self._built = False
        # Debounce state
        self._dirty = False
        self._persist_timer: threading.Timer | None = None
        # Clean up any stale PID-stamped .tmp files left by previous crashes.
        # Each process uses its own .tmp name so concurrent instances don't collide.
        try:
            for stale in self._cache_path.parent.glob(f"{self._cache_path.stem}.*.tmp"):
                stale.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def build(self) -> None:
        """Populate the index at startup, using the on-disk cache when possible."""
        loaded_at, forward = self._load_cache()
        if loaded_at is not None and forward is not None:
            self._build_incremental(forward, loaded_at)
        else:
            self._build_full()
        # Immediate persist after build — no debounce needed here
        self._persist_now()

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
        logger.info("BacklinkIndex: watchdog observer started (cache at %s)", self._cache_path)

    def stop(self) -> None:
        """Stop the watchdog observer thread and flush any pending persist."""
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("BacklinkIndex: watchdog observer stopped")
        # Cancel any pending debounce timer and write immediately
        self._cancel_timer()
        self._persist_now()

    def find(self, target_path: str) -> list[str]:
        """Return sorted list of paths that link to *target_path*'s stem. O(1)."""
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
        reverse: dict[str, set[str]] = {}
        for path, stems in loaded_forward.items():
            for stem in stems:
                reverse.setdefault(stem, set()).add(path)

        stale: list[Path] = []
        deleted: list[str] = []
        current_rels: set[str] = set()

        for md_path in self._vault.rglob("*.md"):
            if not md_path.is_file() or _is_excluded(md_path, self._vault):
                continue
            rel = self._rel(md_path)
            current_rels.add(rel)
            try:
                if md_path.stat().st_mtime > loaded_at:
                    stale.append(md_path)
            except OSError:
                continue

        for rel in loaded_forward:
            if rel not in current_rels:
                deleted.append(rel)

        logger.info(
            "BacklinkIndex: incremental load — cache had %d notes, %d stale, %d deleted",
            len(loaded_forward), len(stale), len(deleted),
        )

        for rel in deleted:
            old_stems = loaded_forward.pop(rel, set())
            for stem in old_stems:
                reverse.get(stem, set()).discard(rel)
                if not reverse.get(stem):
                    reverse.pop(stem, None)

        for md_path in stale:
            rel = self._rel(md_path)
            old_stems = loaded_forward.pop(rel, set())
            for stem in old_stems:
                reverse.get(stem, set()).discard(rel)
                if not reverse.get(stem):
                    reverse.pop(stem, None)
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
        """Try to load the on-disk cache. Returns (saved_at, forward) or (None, None)."""
        if not self._cache_path.exists():
            logger.debug("BacklinkIndex: no cache file at %s", self._cache_path)
            return None, None

        try:
            raw: dict[str, Any] = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("BacklinkIndex: cache unreadable (%s), will full-scan", exc)
            return None, None

        if raw.get("version") != _INDEX_VERSION:
            logger.warning("BacklinkIndex: cache version mismatch, will full-scan")
            return None, None
        if raw.get("vault") != str(self._vault):
            logger.warning("BacklinkIndex: cache is for a different vault, will full-scan")
            return None, None

        saved_at = raw.get("saved_at")
        raw_forward = raw.get("forward")

        if not isinstance(saved_at, (int, float)) or not isinstance(raw_forward, dict):
            logger.warning("BacklinkIndex: cache schema invalid, will full-scan")
            return None, None

        forward: dict[str, set[str]] = {
            path: set(stems) for path, stems in raw_forward.items()
        }
        logger.info(
            "BacklinkIndex: loaded cache (%d notes, saved %.0fs ago)",
            len(forward), time.time() - saved_at,
        )
        return float(saved_at), forward

    def _persist_now(self) -> None:
        """Write the cache to disk immediately. Never raises.

        Uses a PID-stamped .tmp file so concurrent MCP server processes
        (e.g. two Claude Desktop windows on the same vault) never collide
        on the same temp path.
        """
        try:
            with self._lock:
                forward_snapshot = {
                    path: sorted(stems)
                    for path, stems in self._forward.items()
                }
            payload = {
                "version": _INDEX_VERSION,
                "vault": str(self._vault),
                "saved_at": time.time(),
                "forward": forward_snapshot,
            }
            # PID-stamped tmp: each process writes its own file, so two
            # concurrent instances never fight over the same handle.
            tmp = self._cache_path.with_suffix(f".{os.getpid()}.tmp")
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            tmp.write_text(json.dumps(payload, indent=None, separators=(",", ":")), encoding="utf-8")
            # Windows won't rename over an existing open file — delete dest first.
            # Last writer wins; both processes write the same logical content so
            # correctness is unaffected.
            try:
                self._cache_path.unlink(missing_ok=True)
            except OSError:
                pass
            tmp.replace(self._cache_path)
            self._dirty = False
            logger.debug("BacklinkIndex: persisted %d entries to %s", len(forward_snapshot), self._cache_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("BacklinkIndex: failed to persist cache: %s", exc)

    def _schedule_persist(self) -> None:
        """Mark dirty and (re)start the debounce timer."""
        self._dirty = True
        self._cancel_timer()
        timer = threading.Timer(_PERSIST_DEBOUNCE_S, self._persist_now)
        timer.daemon = True
        timer.start()
        self._persist_timer = timer

    def _cancel_timer(self) -> None:
        if self._persist_timer is not None:
            self._persist_timer.cancel()
            self._persist_timer = None

    # ------------------------------------------------------------------ #
    # Internal: incremental update helpers (called from watchdog + service)
    # ------------------------------------------------------------------ #

    def _remove_file(self, rel: str) -> None:
        with self._lock:
            old_stems = self._forward.pop(rel, set())
            for stem in old_stems:
                self._reverse.get(stem, set()).discard(rel)
                if not self._reverse.get(stem):
                    self._reverse.pop(stem, None)
        self._schedule_persist()

    def _add_file(self, abs_path: Path) -> None:
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
        self._schedule_persist()

    def _update_file(self, abs_path: Path) -> None:
        if _is_excluded(abs_path, self._vault):
            return
        rel = self._rel(abs_path)
        stems = self._read_stems(abs_path)
        with self._lock:
            old_stems = self._forward.pop(rel, set())
            for stem in old_stems:
                self._reverse.get(stem, set()).discard(rel)
                if not self._reverse.get(stem):
                    self._reverse.pop(stem, None)
            if stems is not None:
                self._forward[rel] = stems
                for stem in stems:
                    self._reverse.setdefault(stem, set()).add(rel)
        self._schedule_persist()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _read_stems(self, abs_path: Path) -> set[str] | None:
        try:
            return _extract_link_stems(abs_path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            return None

    def _rel(self, abs_path: Path) -> str:
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
        logger.debug("BacklinkIndex: deleted %s", event.src_path)
        self._index._remove_file(self._index._rel(Path(event.src_path)))

    def on_modified(self, event: FileModifiedEvent) -> None:
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        logger.debug("BacklinkIndex: modified %s", event.src_path)
        self._index._update_file(Path(event.src_path))

    def on_moved(self, event: FileMovedEvent) -> None:
        if event.is_directory:
            return
        if event.src_path.endswith(".md"):
            logger.debug("BacklinkIndex: moved (src) %s", event.src_path)
            self._index._remove_file(self._index._rel(Path(event.src_path)))
        if event.dest_path.endswith(".md"):
            logger.debug("BacklinkIndex: moved (dst) %s", event.dest_path)
            self._index._add_file(Path(event.dest_path))