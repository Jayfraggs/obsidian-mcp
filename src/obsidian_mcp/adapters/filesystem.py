"""Filesystem adapter – direct pathlib access to vault .md files.

Replicates the raw I/O that ``VaultService`` previously did inline,
using the project's own ``VaultPathResolver`` and error types so
behaviour is identical to the original code.

PERF FIXES (2026-06):
- list_files / list_folders now skip .git, .obsidian internals, and
  any directory starting with '.' plus the copilot/ folder.
- search_notes scores path+content but skips excluded dirs.
- Added _EXCLUDED_DIRS constant for easy tuning.
"""

from __future__ import annotations

import logging
from pathlib import Path
from shutil import move
from typing import Any

from rapidfuzz import fuzz

from obsidian_mcp.errors import NoteNotFoundError, NoteAlreadyExistsError
from obsidian_mcp.vault.paths import VaultPathResolver
from .base import ObsidianAdapter, RawNote, RawSearchResult

logger = logging.getLogger("obsidian_mcp.adapters.filesystem")

# Directories (by name) to skip during any recursive scan.
_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({
    ".git",
    ".obsidian",   # Obsidian config; not user notes
    "copilot",     # GitHub Copilot cache
    ".trash",      # Obsidian trash
    "node_modules",
})


def _is_excluded(path: Path, vault_root: Path) -> bool:
    """Return True if *path* is inside (or is) an excluded directory."""
    try:
        rel = path.relative_to(vault_root)
    except ValueError:
        return False
    # Check every path component against the excluded set.
    return any(part in _EXCLUDED_DIR_NAMES or part.startswith(".") for part in rel.parts[:-1])


class FilesystemAdapter(ObsidianAdapter):
    """Read/write vault notes directly from disk via pathlib."""

    def __init__(self, vault_path: Path) -> None:
        self.resolver = VaultPathResolver(vault_path)
        self._vault = vault_path.resolve()
        logger.info("FilesystemAdapter active → %s", self._vault)

    # ------------------------------------------------------------------ #
    # Note CRUD
    # ------------------------------------------------------------------ #

    def read_note(self, path: str) -> RawNote:
        note_path = self.resolver.resolve_note_path(path)
        if not note_path.exists() or not note_path.is_file():
            return RawNote(
                path=self.resolver.to_vault_relative(note_path),
                content="",
                exists=False,
            )
        content = note_path.read_text(encoding="utf-8")
        return RawNote(
            path=self.resolver.to_vault_relative(note_path),
            content=content,
        )

    def write_note(self, path: str, content: str) -> None:
        note_path = self.resolver.resolve_note_path(path)
        note_path.parent.mkdir(parents=True, exist_ok=True)
        note_path.write_text(content, encoding="utf-8")
        logger.debug("Wrote note: %s", path)

    def append_note(self, path: str, content: str) -> None:
        note_path = self.resolver.resolve_note_path(path)
        self._require_exists(note_path)
        current = note_path.read_text(encoding="utf-8")
        separator = "" if current.endswith("\n") or not current else "\n"
        note_path.write_text(current + separator + content, encoding="utf-8")

    def delete_note(self, path: str) -> None:
        note_path = self.resolver.resolve_note_path(path)
        self._require_exists(note_path)
        note_path.unlink()
        logger.debug("Deleted note: %s", path)

    def move_note(self, source: str, destination: str) -> None:
        src = self.resolver.resolve_note_path(source)
        dst = self.resolver.resolve_note_path(destination)
        self._require_exists(src)
        if dst.exists():
            raise NoteAlreadyExistsError("Destination note already exists.")
        dst.parent.mkdir(parents=True, exist_ok=True)
        move(str(src), str(dst))
        logger.debug("Moved note: %s → %s", source, destination)

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def list_files(self) -> list[str]:
        return sorted(
            self.resolver.to_vault_relative(p)
            for p in self._vault.rglob("*")
            if p.is_file() and not _is_excluded(p, self._vault)
        )

    def list_folders(self) -> list[str]:
        return sorted(
            self.resolver.to_vault_relative(p)
            for p in self._vault.rglob("*")
            if p.is_dir() and not _is_excluded(p, self._vault)
            # Also skip the excluded dirs themselves
            and p.name not in _EXCLUDED_DIR_NAMES
            and not p.name.startswith(".")
        )

    def search_notes(self, query: str, limit: int = 10) -> list[RawSearchResult]:
        normalized = query.strip()
        if not normalized:
            return []
        results: list[RawSearchResult] = []
        for note_path in self._vault.rglob("*.md"):
            if not note_path.is_file():
                continue
            if _is_excluded(note_path, self._vault):
                continue
            try:
                content = note_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            score = fuzz.partial_ratio(normalized.lower(), content.lower())
            if score <= 0:
                continue
            results.append(RawSearchResult(
                path=self.resolver.to_vault_relative(note_path),
                score=round(float(score), 2),
                preview=self._preview(content, normalized),
            ))
        return sorted(results, key=lambda r: (-r.score, r.path))[:limit]

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #

    def health_check(self) -> bool:
        return self._vault.exists() and self._vault.is_dir()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _require_exists(note_path: Path) -> None:
        if not note_path.exists() or not note_path.is_file():
            raise NoteNotFoundError("Note was not found.")

    @staticmethod
    def _preview(content: str, query: str) -> str:
        lower = content.lower()
        idx = lower.find(query.lower())
        if idx == -1:
            return content[:120]
        start = max(idx - 40, 0)
        end = min(idx + len(query) + 80, len(content))
        return content[start:end]
