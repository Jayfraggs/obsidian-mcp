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

FIND-REPLACE UPDATE:
- str_replace_vault now accepts exception_rules, dry_run, backup,
  and whole_word parameters. See method docstring for full details.
"""

from __future__ import annotations

import logging
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

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

# Backup folder name at vault root (hidden from Obsidian file explorer).
_BACKUP_DIR = ".mcp-backups"


class ExceptionRule(TypedDict):
    """A single exception rule for str_replace_vault.

    type:
        One of: "folder", "tag", "frontmatter", "path_glob", "contains_string"
    value:
        The value to match against for that rule type.

    Examples
    --------
    {"type": "folder",          "value": "30-References"}
    {"type": "tag",             "value": "#archived"}
    {"type": "frontmatter",     "value": "status: locked"}
    {"type": "path_glob",       "value": "Templates"}
    {"type": "contains_string", "value": "DO NOT EDIT"}
    """

    type: str
    value: str


def _note_matches_exception(
    vault_rel: str,
    content: str,
    rules: list[ExceptionRule],
) -> tuple[bool, str]:
    """Return (True, reason) if any exception rule matches; (False, "") otherwise.

    Rules use OR logic: the first matching rule wins and the note is skipped.

    Parameters
    ----------
    vault_rel:
        Vault-relative path of the note (e.g. "Projects/Foo.md").
    content:
        Full text content of the note.
    rules:
        List of ExceptionRule dicts supplied by the caller.
    """
    for rule in rules:
        rule_type = rule.get("type", "")
        rule_value = rule.get("value", "")

        if rule_type == "folder":
            # Match if the note's path starts with the given folder prefix.
            prefix = rule_value.rstrip("/") + "/"
            if vault_rel.startswith(prefix) or f"/{rule_value.rstrip('/')}/" in f"/{vault_rel}":
                return True, f"folder rule matched '{rule_value}'"

        elif rule_type == "tag":
            # Match Obsidian inline tags: #tagname (space or end-of-line boundary).
            tag = rule_value if rule_value.startswith("#") else f"#{rule_value}"
            # Simple check: tag appears in content followed by space, newline, or EOF.
            pattern = re.escape(tag) + r"(?=[\s,\]]|$)"
            if re.search(pattern, content, re.MULTILINE):
                return True, f"tag rule matched '{rule_value}'"

        elif rule_type == "frontmatter":
            # Match a key: value substring inside the YAML frontmatter block.
            fm_match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if fm_match and rule_value in fm_match.group(1):
                return True, f"frontmatter rule matched '{rule_value}'"

        elif rule_type == "path_glob":
            # Match if vault_rel contains the given substring.
            if rule_value in vault_rel:
                return True, f"path_glob rule matched '{rule_value}'"

        elif rule_type == "contains_string":
            # Match if the note body contains the sentinel string.
            if rule_value in content:
                return True, f"contains_string rule matched '{rule_value}'"

        else:
            logger.warning("Unknown exception rule type '%s' — skipping", rule_type)

    return False, ""


def _build_search_pattern(old_str: str, *, whole_word: bool, case_sensitive: bool) -> re.Pattern[str]:
    """Compile a search pattern for the given options.

    For whole_word=True on hyphenated strings (e.g. "DeepSeek-V4-Flash"),
    \\b anchors are unreliable because hyphens break word boundaries.
    Instead we assert that the match is not immediately preceded or followed
    by an alphanumeric character, which is the correct semantic for
    model-name–style identifiers.
    """
    escaped = re.escape(old_str)
    if whole_word:
        # Exclude alphanumeric AND hyphen from boundaries so that
        # "DeepSeek-V4-Flash" does not match inside "DeepSeek-V4-Flash-Lite".
        pattern = rf"(?<![A-Za-z0-9\-]){escaped}(?![A-Za-z0-9\-])"
    else:
        pattern = escaped
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(pattern, flags)


def _apply_replacement(
    content: str,
    pattern: re.Pattern[str],
    new_str: str,
    *,
    require_unique_per_note: bool,
) -> tuple[str | None, str | None]:
    """Return (new_content, None) on success or (None, error_reason) on skip.

    Returns None for new_content if the content would be unchanged.
    """
    matches = list(pattern.finditer(content))
    count = len(matches)

    if count == 0:
        return None, None  # unchanged — not an error

    if count > 1 and require_unique_per_note:
        return None, f"ambiguous — {count} occurrences found"

    new_content = pattern.sub(new_str, content) if not require_unique_per_note else content[:matches[0].start()] + new_str + content[matches[0].end():]
    return new_content, None


class VaultService:
    """Perform safe operations inside an Obsidian vault."""

    _FILE_LIST_TTL = 5.0  # seconds

    def __init__(
        self,
        vault_path: Path,
        adapter: ObsidianAdapter | None = None,
    ) -> None:
        self.resolver = VaultPathResolver(vault_path)
        self._vault_path = vault_path
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
        whole_word: bool = False,
        case_sensitive: bool = True,
        dry_run: bool = True,
        backup: bool = False,
        exception_rules: list[ExceptionRule] | None = None,
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
            matching note are replaced.
        path_glob:
            Optional substring filter — only notes whose vault-relative
            path contains this substring are considered.
        whole_word:
            If True, only match old_str when it is not immediately preceded
            or followed by an alphanumeric character. Safe for hyphenated
            strings like "DeepSeek-V4-Flash" (unlike \\b anchors).
        case_sensitive:
            If False, matching is case-insensitive. Default True.
        dry_run:
            If True (default), no files are written or backed up. Returns
            a full preview of what would be changed and skipped.
            Always run dry_run=True first to verify before committing.
        backup:
            If True (and dry_run=False), copies each affected note to
            .mcp-backups/<timestamp>/<vault-relative-path> before writing.
            Backups are never created during a dry run.
        exception_rules:
            List of rules. If a note matches ANY rule it is skipped.
            Each rule is a dict with keys "type" and "value".

            Supported types:
              "folder"          — skip notes inside this folder
                                  e.g. {"type": "folder", "value": "30-References"}
              "tag"             — skip notes containing this Obsidian tag
                                  e.g. {"type": "tag", "value": "#archived"}
              "frontmatter"     — skip notes whose YAML frontmatter contains
                                  this key:value substring
                                  e.g. {"type": "frontmatter", "value": "status: locked"}
              "path_glob"       — skip notes whose path contains this substring
                                  e.g. {"type": "path_glob", "value": "Templates"}
              "contains_string" — skip notes that contain this sentinel string
                                  e.g. {"type": "contains_string", "value": "DO NOT EDIT"}

        Returns
        -------
        dict with keys:
            dry_run        — bool, whether this was a preview run
            updated        — list of vault-relative paths changed (or would change)
            skipped        — list of {path, reason} dicts for exception-skipped notes
            ambiguous      — list of paths skipped due to >1 occurrence
                             (only when require_unique_per_note=True)
            unchanged_count — count of notes scanned with zero occurrences
            backup_dir     — str path of backup directory (None if backup=False or dry_run)
        """
        rules: list[ExceptionRule] = exception_rules or []
        pattern = _build_search_pattern(old_str, whole_word=whole_word, case_sensitive=case_sensitive)

        updated: list[str] = []
        skipped: list[dict[str, str]] = []
        ambiguous: list[str] = []
        unchanged_count = 0
        backup_dir: str | None = None

        # Determine backup directory once per call (timestamp-stamped).
        if backup and not dry_run:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_root = self._vault_path / _BACKUP_DIR / ts
            backup_dir = str(backup_root)

        for file_path in self.list_files():
            if not file_path.endswith(".md"):
                continue
            if path_glob and path_glob not in file_path:
                continue

            raw = self._adapter.read_note(file_path)
            if not raw.exists:
                continue

            # --- Exception rules check ---
            matched_exception, reason = _note_matches_exception(file_path, raw.content, rules)
            if matched_exception:
                skipped.append({"path": file_path, "reason": reason})
                continue

            # --- Replacement logic ---
            new_content, error_reason = _apply_replacement(
                raw.content,
                pattern,
                new_str,
                require_unique_per_note=require_unique_per_note,
            )

            if error_reason:
                ambiguous.append(file_path)
                continue

            if new_content is None:
                # No occurrences found in this note.
                unchanged_count += 1
                continue

            # Content would/will change.
            if not dry_run:
                # Optionally back up before writing.
                if backup and backup_dir:
                    self._backup_note(file_path, raw.content, backup_root)

                self._adapter.write_note(file_path, new_content)
                note_path = self.resolver.resolve_note_path(file_path)
                self._index._update_file(note_path)

            updated.append(file_path)

        if updated and not dry_run:
            self._invalidate_file_list()

        return {
            "dry_run": dry_run,
            "updated": updated,
            "skipped": skipped,
            "ambiguous": ambiguous,
            "unchanged_count": unchanged_count,
            "backup_dir": backup_dir,
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

    def _backup_note(self, vault_rel: str, content: str, backup_root: Path) -> None:
        """Write *content* to backup_root / vault_rel, creating dirs as needed."""
        dest = backup_root / vault_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        logger.debug("Backed up note: %s → %s", vault_rel, dest)

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
