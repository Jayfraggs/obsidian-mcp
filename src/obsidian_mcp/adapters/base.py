"""Abstract base for all Obsidian vault adapters.

Every adapter exposes the same synchronous interface so that
``VaultService`` can treat them interchangeably.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawNote:
    """Raw vault-level note data returned by adapters."""

    path: str          # vault-relative POSIX path
    content: str       # full file text (frontmatter + body)
    exists: bool = True


@dataclass
class RawSearchResult:
    """Single fuzzy-search hit returned by adapters."""

    path: str
    score: float
    preview: str


class ObsidianAdapter(ABC):
    """Synchronous contract that all vault adapters must implement."""

    # ------------------------------------------------------------------ #
    # Note CRUD
    # ------------------------------------------------------------------ #

    @abstractmethod
    def read_note(self, path: str) -> RawNote:
        """Return the raw content of a note, or RawNote(exists=False)."""

    @abstractmethod
    def write_note(self, path: str, content: str) -> None:
        """Create or fully overwrite a note."""

    @abstractmethod
    def append_note(self, path: str, content: str) -> None:
        """Append *content* to an existing note."""

    @abstractmethod
    def delete_note(self, path: str) -> None:
        """Delete a note.  Raise NoteNotFoundError if it does not exist."""

    @abstractmethod
    def move_note(self, source: str, destination: str) -> None:
        """Move a note from *source* to *destination*."""

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    @abstractmethod
    def list_files(self) -> list[str]:
        """Return all vault-relative file paths (not just .md)."""

    @abstractmethod
    def list_folders(self) -> list[str]:
        """Return all vault-relative directory paths."""

    @abstractmethod
    def search_notes(self, query: str, limit: int = 10) -> list[RawSearchResult]:
        """Return fuzzy-ranked search results."""

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #

    @abstractmethod
    def health_check(self) -> bool:
        """Return True if this adapter can currently reach the vault."""
