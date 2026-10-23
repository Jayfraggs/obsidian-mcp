"""Service layer for Obsidian vault note and file operations.

``VaultService`` is now adapter-backed: all raw filesystem (or REST API)
I/O is delegated to an ``ObsidianAdapter``.  The public method signatures
and return shapes are **identical** to the original implementation so that
``KnowledgeService``, all MCP tools, and the Web UI need zero changes.

Construction
------------
    # Original (still works – uses FilesystemAdapter automatically):
    svc = VaultService(vault_path)

    # Adapter-aware (preferred from __main__ / web app):
    adapter = AutoAdapter.from_settings(settings)
    svc = VaultService(vault_path, adapter=adapter)

PERF FIXES (2026-06):
- BacklinkIndex (vault/index.py) provides O(1) find_backlinks via an
  inverted dict built once at startup and kept live by a watchdog thread.
- read_note defaults include_backlinks=False; callers opt in explicitly.
- list_files has a 5-second TTL cache to avoid repeated rglob calls.
- write/move/delete mutations notify the index directly so it stays
  consistent even if watchdog events arrive with a small delay.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

from obsidian_mcp.adapters.base import ObsidianAdapter, RawNote
from obsidian_mcp.adapters.filesystem import FilesystemAdapter
from obsidian_mcp.errors import (
    NoteAlreadyExistsError,
    NoteNotFoundError,
    StringNotFoundError,
    StringNotUniqueError,
)
from obsidian_mcp.vault.index import BacklinkIndex
from obsidian_mcp.vault.metadata import extract_note_metadata
from obsidian_mcp.vault.paths import VaultPathResolver

logger = logging.getLogger("obsidian_mcp.vault.service")

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)")


class VaultService:
    """Perform safe operations inside an Obsidian vault."""

    _FILE_LIST_TTL = 5.0  # seconds

    def __init__(
        self,
        vault_path: Path,
        adapter: ObsidianAdapter | None = None,
    ) -> None:
        self.resolver = VaultPathResolver(vault_path)
        self._adapter: ObsidianAdapter = (
            adapter if adapter is not None else FilesystemAdapter(vault_path)
        )
        self._file_list_cache: tuple[list[str], float] | None = None
        self._index = BacklinkIndex(vault_path)

    # ------------------------------------------------------------------ #
    # Lifecycle  (call from __main__.py around server.run())
    # ------------------------------------------------------------------ #

    def start(self) -> None:
        """Build the backlink index and start the watchdog observer.

        Must be called once before serving MCP requests.
        """
        self._index.build()
        self._index.start()
        logger.info("VaultService started (index ready, watcher running)")

    def stop(self) -> None:
        """Shut down the watchdog observer thread cleanly."""
        self._index.stop()
        logger.info("VaultService stopped")

    # ------------------------------------------------------------------ #
    # Note CRUD
    # ------------------------------------------------------------------ #

    def create_note(self, path: str, content: str) -> dict[str, Any]:
        """Create a new markdown note."""
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        existing = self._adapter.read_note(vault_rel)
        if existing.exists:
            raise NoteAlreadyExistsError("Note already exists.")
        self._adapter.write_note(vault_rel, content)
        self._invalidate_file_list()
        # Eagerly update index (watchdog may lag by ~100 ms)
        self._index._add_file(note_path)
        return self._note_payload(vault_rel, content)

    def read_note(self, path: str, *, include_backlinks: bool = False) -> dict[str, Any]:
        """Read a markdown note with metadata.

        Backlinks default to an empty list. Pass ``include_backlinks=True``
        only when the caller explicitly needs them — the index makes it O(1)
        but it still adds a dict lookup + set copy per call.
        """
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        raw = self._adapter.read_note(vault_rel)
        if not raw.exists:
            raise NoteNotFoundError("Note was not found.")
        payload = self._note_payload(vault_rel, raw.content)
        payload["backlinks"] = self.find_backlinks(path) if include_backlinks else []
        return payload

    def update_note(self, path: str, content: str) -> dict[str, Any]:
        """Replace the full contents of a markdown note."""
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        raw = self._adapter.read_note(vault_rel)
        if not raw.exists:
            raise NoteNotFoundError("Note was not found.")
        self._adapter.write_note(vault_rel, content)
        # Update index with new link set for this note
        self._index._update_file(note_path)
        return self._note_payload(vault_rel, content)

    def append_note(self, path: str, content: str) -> dict[str, Any]:
        """Append content to a markdown note."""
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        raw = self._adapter.read_note(vault_rel)
        if not raw.exists:
            raise NoteNotFoundError("Note was not found.")
        self._adapter.append_note(vault_rel, content)
        updated = self._adapter.read_note(vault_rel)
        # Re-index: appended content may add new wikilinks
        self._index._update_file(note_path)
        return self._note_payload(vault_rel, updated.content)

    def str_replace_note(
        self,
        path: str,
        old_str: str,
        new_str: str = "",
    ) -> dict[str, Any]:
        """Replace one exact occurrence of *old_str* with *new_str* in a note.

        Mirrors the computer-use str_replace tool: *old_str* must match the
        raw note content exactly and appear exactly once. This avoids the
        cost and risk of resending an entire note via update_note just to
        change one line — and the uniqueness check prevents silently
        editing the wrong occurrence when a phrase repeats.

        Raises
        ------
        NoteNotFoundError
            If the note does not exist.
        StringNotFoundError
            If old_str does not occur anywhere in the note.
        StringNotUniqueError
            If old_str occurs more than once — the caller must supply
            more surrounding context to make the match unique.
        """
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        raw = self._adapter.read_note(vault_rel)
        if not raw.exists:
            raise NoteNotFoundError("Note was not found.")

        occurrences = raw.content.count(old_str)
        if occurrences == 0:
            raise StringNotFoundError(
                f"old_str was not found in '{vault_rel}'.",
                internal_detail=f"old_str={old_str!r}",
            )
        if occurrences > 1:
            raise StringNotUniqueError(
                f"old_str occurs {occurrences} times in '{vault_rel}' — it must be unique. "
                "Include more surrounding context in old_str to disambiguate.",
                internal_detail=f"old_str={old_str!r} occurrences={occurrences}",
            )

        new_content = raw.content.replace(old_str, new_str, 1)
        self._adapter.write_note(vault_rel, new_content)
        self._index._update_file(note_path)
        return self._note_payload(vault_rel, new_content)

    def str_replace_vault(
        self,
        old_str: str,
        new_str: str = "",
        *,
        require_unique_per_note: bool = True,
        path_glob: str | None = None,
    ) -> dict[str, Any]:
        """Replace *old_str* with *new_str* across every matching note in the vault.

        Unlike str_replace_note, this is a best-effort batch operation:
        one note failing to match does not abort the rest. Every note is
        attempted and the outcome is reported per-path.

        Parameters
        ----------
        old_str:
            Exact text to search for in each note.
        new_str:
            Replacement text.
        require_unique_per_note:
            If True (default), a note where old_str occurs more than once
            is skipped and reported under "ambiguous" rather than guessing
            which occurrence to replace. If False, ALL occurrences in a
            matching note are replaced (str.replace with no count limit) —
            use this only when you specifically want a global substitution
            and have verified old_str is unambiguous in context.
        path_glob:
            Optional substring filter — only notes whose vault-relative
            path contains this substring are considered. Pass a folder
            prefix (e.g. "Projects/") to scope the replacement.

        Returns
        -------
        dict with keys:
            updated    — list of vault-relative paths successfully changed
            ambiguous  — list of paths skipped due to >1 occurrence
                         (only populated when require_unique_per_note=True)
            unchanged  — count of notes scanned with zero occurrences
        """
        updated: list[str] = []
        ambiguous: list[str] = []
        unchanged_count = 0

        for file_path in self.list_files():
            if not file_path.endswith(".md"):
                continue
            if path_glob and path_glob not in file_path:
                continue

            raw = self._adapter.read_note(file_path)
            if not raw.exists:
                continue

            occurrences = raw.content.count(old_str)
            if occurrences == 0:
                unchanged_count += 1
                continue

            if occurrences > 1 and require_unique_per_note:
                ambiguous.append(file_path)
                continue

            count = 1 if require_unique_per_note else -1  # -1 = replace all (str.replace semantics)
            new_content = raw.content.replace(old_str, new_str, count) if count > 0 else raw.content.replace(old_str, new_str)
            self._adapter.write_note(file_path, new_content)
            note_path = self.resolver.resolve_note_path(file_path)
            self._index._update_file(note_path)
            updated.append(file_path)

        if updated:
            self._invalidate_file_list()

        return {
            "updated": updated,
            "ambiguous": ambiguous,
            "unchanged_count": unchanged_count,
        }

    def delete_note(self, path: str) -> dict[str, Any]:
        """Delete a markdown note."""
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        raw = self._adapter.read_note(vault_rel)
        if not raw.exists:
            raise NoteNotFoundError("Note was not found.")
        self._adapter.delete_note(vault_rel)
        self._invalidate_file_list()
        self._index._remove_file(vault_rel)
        return {"path": vault_rel, "deleted": True}

    def move_note(self, source: str, destination: str) -> dict[str, str]:
        """Move a markdown note to another vault-relative path."""
        src_path = self.resolver.resolve_note_path(source)
        dst_path = self.resolver.resolve_note_path(destination)
        src_rel = self.resolver.to_vault_relative(src_path)
        dst_rel = self.resolver.to_vault_relative(dst_path)
        self._adapter.move_note(src_rel, dst_rel)
        self._invalidate_file_list()
        self._index._remove_file(src_rel)
        self._index._add_file(dst_path)
        return {"from": src_rel, "to": dst_rel}

    def rename_note(self, path: str, new_name: str) -> dict[str, str]:
        """Rename a markdown note within its current folder."""
        src_path = self.resolver.resolve_note_path(path)
        dst_path = src_path.with_name(self._note_filename(new_name))
        src_rel = self.resolver.to_vault_relative(src_path)
        dst_rel = self.resolver.to_vault_relative(dst_path)
        self._adapter.move_note(src_rel, dst_rel)
        self._invalidate_file_list()
        # Stem changes on rename: src entries must be dropped, dst re-indexed.
        # Also: any note linking to the old stem will now be a broken link —
        # that's a user concern, not something we fix automatically.
        self._index._remove_file(src_rel)
        self._index._add_file(dst_path)
        return {"from": src_rel, "to": dst_rel}

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def list_files(self) -> list[str]:
        """List all files in the vault (cached for _FILE_LIST_TTL seconds)."""
        now = time.monotonic()
        if self._file_list_cache is not None:
            files, ts = self._file_list_cache
            if now - ts < self._FILE_LIST_TTL:
                return files
        files = self._adapter.list_files()
        self._file_list_cache = (files, now)
        return files

    def list_folders(self) -> list[str]:
        """List all folders in the vault."""
        return self._adapter.list_folders()

    def search_notes(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search markdown notes using the adapter's fuzzy ranking."""
        raw_results = self._adapter.search_notes(query, limit)
        return [
            {"path": r.path, "score": r.score, "preview": r.preview}
            for r in raw_results
        ]

    def find_backlinks(self, target_path: str) -> list[str]:
        """Return sorted paths that link to *target_path*.

        Uses the BacklinkIndex for O(1) lookup when the index is ready.
        Falls back to a linear scan only if called before start() (e.g.
        in tests that don't call the full lifecycle).
        """
        if self._index.is_ready():
            return self._index.find(target_path)

        # Fallback: linear scan (should not happen in production)
        logger.warning("find_backlinks called before index is ready — falling back to linear scan")
        return self._find_backlinks_linear(target_path)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _find_backlinks_linear(self, target_path: str) -> list[str]:
        """O(N) fallback used only before the index is built."""
        target = self.resolver.resolve_note_path(target_path)
        target_stem = target.stem.lower()
        vault_rel_target = self.resolver.to_vault_relative(target)
        backlinks: list[str] = []
        for file_path in self.list_files():
            if not file_path.endswith(".md"):
                continue
            raw = self._adapter.read_note(file_path)
            if not raw.exists or raw.path == vault_rel_target:
                continue
            for m in _WIKILINK_RE.finditer(raw.content):
                if Path(m.group(1).strip()).stem.lower() == target_stem:
                    backlinks.append(file_path)
                    break
        return sorted(backlinks)

    def _note_payload(self, vault_rel: str, content: str) -> dict[str, Any]:
        metadata = extract_note_metadata(vault_rel, content)
        return {
            "path": vault_rel,
            "content": content,
            "metadata": metadata.to_dict(),
        }

    def _invalidate_file_list(self) -> None:
        self._file_list_cache = None

    @staticmethod
    def _note_filename(name: str) -> str:
        stripped = name.strip()
        return stripped if stripped.endswith(".md") else f"{stripped}.md"
