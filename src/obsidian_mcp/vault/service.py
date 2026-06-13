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
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from obsidian_mcp.adapters.base import ObsidianAdapter, RawNote
from obsidian_mcp.adapters.filesystem import FilesystemAdapter
from obsidian_mcp.errors import NoteAlreadyExistsError, NoteNotFoundError
from obsidian_mcp.vault.metadata import extract_note_metadata
from obsidian_mcp.vault.paths import VaultPathResolver


class VaultService:
    """Perform safe operations inside an Obsidian vault."""

    def __init__(
        self,
        vault_path: Path,
        adapter: ObsidianAdapter | None = None,
    ) -> None:
        self.resolver = VaultPathResolver(vault_path)
        # Default to FilesystemAdapter so existing callers that pass only
        # vault_path continue to work without any modification.
        self._adapter: ObsidianAdapter = (
            adapter if adapter is not None else FilesystemAdapter(vault_path)
        )

    # ------------------------------------------------------------------ #
    # Note CRUD
    # ------------------------------------------------------------------ #

    def create_note(self, path: str, content: str) -> dict[str, Any]:
        """Create a new markdown note."""
        # Resolve to check path safety; existence check via adapter.
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        existing = self._adapter.read_note(vault_rel)
        if existing.exists:
            raise NoteAlreadyExistsError("Note already exists.")
        self._adapter.write_note(vault_rel, content)
        return self._note_payload(vault_rel, content)

    def read_note(self, path: str) -> dict[str, Any]:
        """Read a markdown note with metadata and backlinks."""
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        raw = self._adapter.read_note(vault_rel)
        if not raw.exists:
            raise NoteNotFoundError("Note was not found.")
        payload = self._note_payload(vault_rel, raw.content)
        payload["backlinks"] = self.find_backlinks(path)
        return payload

    def update_note(self, path: str, content: str) -> dict[str, Any]:
        """Replace the full contents of a markdown note."""
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        raw = self._adapter.read_note(vault_rel)
        if not raw.exists:
            raise NoteNotFoundError("Note was not found.")
        self._adapter.write_note(vault_rel, content)
        return self._note_payload(vault_rel, content)

    def append_note(self, path: str, content: str) -> dict[str, Any]:
        """Append content to a markdown note."""
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        raw = self._adapter.read_note(vault_rel)
        if not raw.exists:
            raise NoteNotFoundError("Note was not found.")
        self._adapter.append_note(vault_rel, content)
        # Re-read to get the updated full content for the payload
        updated = self._adapter.read_note(vault_rel)
        return self._note_payload(vault_rel, updated.content)

    def delete_note(self, path: str) -> dict[str, Any]:
        """Delete a markdown note."""
        note_path = self.resolver.resolve_note_path(path)
        vault_rel = self.resolver.to_vault_relative(note_path)
        raw = self._adapter.read_note(vault_rel)
        if not raw.exists:
            raise NoteNotFoundError("Note was not found.")
        self._adapter.delete_note(vault_rel)
        return {"path": vault_rel, "deleted": True}

    def move_note(self, source: str, destination: str) -> dict[str, str]:
        """Move a markdown note to another vault-relative path."""
        src_path = self.resolver.resolve_note_path(source)
        dst_path = self.resolver.resolve_note_path(destination)
        src_rel = self.resolver.to_vault_relative(src_path)
        dst_rel = self.resolver.to_vault_relative(dst_path)
        # adapter.move_note raises NoteNotFoundError / NoteAlreadyExistsError as needed
        self._adapter.move_note(src_rel, dst_rel)
        return {"from": src_rel, "to": dst_rel}

    def rename_note(self, path: str, new_name: str) -> dict[str, str]:
        """Rename a markdown note within its current folder."""
        src_path = self.resolver.resolve_note_path(path)
        dst_path = src_path.with_name(self._note_filename(new_name))
        src_rel = self.resolver.to_vault_relative(src_path)
        dst_rel = self.resolver.to_vault_relative(dst_path)
        self._adapter.move_note(src_rel, dst_rel)
        return {"from": src_rel, "to": dst_rel}

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def list_files(self) -> list[str]:
        """List all files in the vault."""
        return self._adapter.list_files()

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
        """Find notes that link to a target note stem."""
        target = self.resolver.resolve_note_path(target_path)
        target_stem = target.stem
        backlinks: list[str] = []
        for file_path in self._adapter.list_files():
            if not file_path.endswith(".md"):
                continue
            raw = self._adapter.read_note(file_path)
            if not raw.exists or raw.path == self.resolver.to_vault_relative(target):
                continue
            metadata = extract_note_metadata(file_path, raw.content)
            if target_stem in {
                Path(link).stem
                for link in metadata.wikilinks + metadata.markdown_links
            }:
                backlinks.append(file_path)
        return sorted(backlinks)

    # ------------------------------------------------------------------ #
    # Internal helpers (unchanged from original)
    # ------------------------------------------------------------------ #

    def _note_payload(self, vault_rel: str, content: str) -> dict[str, Any]:
        metadata = extract_note_metadata(vault_rel, content)
        return {
            "path": vault_rel,
            "content": content,
            "metadata": metadata.to_dict(),
        }

    @staticmethod
    def _note_filename(name: str) -> str:
        stripped = name.strip()
        return stripped if stripped.endswith(".md") else f"{stripped}.md"
