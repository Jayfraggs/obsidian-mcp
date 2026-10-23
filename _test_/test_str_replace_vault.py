"""Tests for the enhanced str_replace_vault method.

Drop this file into _test_/unit/vault/ and run:
    pytest _test_/unit/vault/test_str_replace_vault.py -v
"""

from pathlib import Path

import pytest

from obsidian_mcp.vault.service import VaultService


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def make_service(tmp_path: Path) -> VaultService:
    return VaultService(tmp_path)


def write_note(service: VaultService, path: str, content: str) -> None:
    service.create_note(path, content)


# ------------------------------------------------------------------ #
# 1. Dry run — no files written
# ------------------------------------------------------------------ #

def test_dry_run_returns_preview_without_writing(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Note", "Hello DeepSeek-V4-Flash world")

    result = svc.str_replace_vault(
        "DeepSeek-V4-Flash", "DeepSeek-V4.1-Flash", dry_run=True
    )

    assert result["dry_run"] is True
    assert "Note.md" in result["updated"]
    # File must NOT have changed on disk.
    content = (tmp_path / "Note.md").read_text(encoding="utf-8")
    assert "DeepSeek-V4-Flash" in content
    assert "DeepSeek-V4.1-Flash" not in content


# ------------------------------------------------------------------ #
# 2. Live run — files written
# ------------------------------------------------------------------ #

def test_live_run_writes_replacement(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Note", "Uses DeepSeek-V4-Flash here")

    result = svc.str_replace_vault(
        "DeepSeek-V4-Flash", "DeepSeek-V4.1-Flash", dry_run=False
    )

    assert result["dry_run"] is False
    assert "Note.md" in result["updated"]
    content = (tmp_path / "Note.md").read_text(encoding="utf-8")
    assert "DeepSeek-V4.1-Flash" in content
    assert "DeepSeek-V4-Flash" not in content


# ------------------------------------------------------------------ #
# 3. Backup
# ------------------------------------------------------------------ #

def test_backup_creates_copy_before_write(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    original = "Original content with OldTerm"
    write_note(svc, "Note", original)

    result = svc.str_replace_vault(
        "OldTerm", "NewTerm", dry_run=False, backup=True
    )

    assert result["backup_dir"] is not None
    backup_root = Path(result["backup_dir"])
    backup_file = backup_root / "Note.md"
    assert backup_file.exists(), "Backup file was not created"
    assert backup_file.read_text(encoding="utf-8") == original


def test_backup_not_created_during_dry_run(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Note", "text OldTerm text")

    result = svc.str_replace_vault(
        "OldTerm", "NewTerm", dry_run=True, backup=True
    )

    assert result["backup_dir"] is None


# ------------------------------------------------------------------ #
# 4. Whole-word matching
# ------------------------------------------------------------------ #

def test_whole_word_does_not_match_substring(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    # "Flash" is a substring of "FlashLight" — whole_word should NOT match.
    write_note(svc, "Note", "Using FlashLight here")

    result = svc.str_replace_vault(
        "Flash", "LED", dry_run=True, whole_word=True
    )

    assert result["updated"] == []
    assert result["unchanged_count"] == 1


def test_whole_word_matches_standalone_token(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Note", "Using Flash here")

    result = svc.str_replace_vault(
        "Flash", "LED", dry_run=True, whole_word=True
    )

    assert "Note.md" in result["updated"]


def test_whole_word_handles_hyphenated_model_name(tmp_path: Path) -> None:
    """DeepSeek-V4-Flash should match exactly, not DeepSeek-V4-Flash-Lite."""
    svc = make_service(tmp_path)
    write_note(svc, "A", "Model: DeepSeek-V4-Flash used here")
    write_note(svc, "B", "Model: DeepSeek-V4-Flash-Lite used here")

    result = svc.str_replace_vault(
        "DeepSeek-V4-Flash", "DeepSeek-V4.1-Flash",
        dry_run=True, whole_word=True
    )

    assert "A.md" in result["updated"]
    assert "B.md" not in result["updated"]


# ------------------------------------------------------------------ #
# 5. Case-insensitive matching
# ------------------------------------------------------------------ #

def test_case_insensitive_matches_mixed_case(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Note", "DEEPSEEK-V4-FLASH is fast")

    result = svc.str_replace_vault(
        "DeepSeek-V4-Flash", "DeepSeek-V4.1-Flash",
        dry_run=True, case_sensitive=False
    )

    assert "Note.md" in result["updated"]


def test_case_sensitive_does_not_match_wrong_case(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Note", "DEEPSEEK-V4-FLASH is fast")

    result = svc.str_replace_vault(
        "DeepSeek-V4-Flash", "DeepSeek-V4.1-Flash",
        dry_run=True, case_sensitive=True
    )

    assert result["updated"] == []


# ------------------------------------------------------------------ #
# 6. Exception rules — folder
# ------------------------------------------------------------------ #

def test_exception_folder_skips_notes_in_folder(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Projects/Active", "Uses OldTerm")
    write_note(svc, "Archive/Old", "Uses OldTerm")

    result = svc.str_replace_vault(
        "OldTerm", "NewTerm",
        dry_run=True,
        exception_rules=[{"type": "folder", "value": "Archive"}],
    )

    assert "Projects/Active.md" in result["updated"]
    assert any(s["path"] == "Archive/Old.md" for s in result["skipped"])


# ------------------------------------------------------------------ #
# 7. Exception rules — tag
# ------------------------------------------------------------------ #

def test_exception_tag_skips_tagged_notes(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Live", "OldTerm here #active")
    write_note(svc, "Dead", "OldTerm here #archived")

    result = svc.str_replace_vault(
        "OldTerm", "NewTerm",
        dry_run=True,
        exception_rules=[{"type": "tag", "value": "#archived"}],
    )

    assert "Live.md" in result["updated"]
    assert any(s["path"] == "Dead.md" for s in result["skipped"])


# ------------------------------------------------------------------ #
# 8. Exception rules — frontmatter
# ------------------------------------------------------------------ #

def test_exception_frontmatter_skips_locked_notes(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Editable", "OldTerm in editable note")
    write_note(svc, "Locked", "---\nstatus: locked\n---\nOldTerm in locked note")

    result = svc.str_replace_vault(
        "OldTerm", "NewTerm",
        dry_run=True,
        exception_rules=[{"type": "frontmatter", "value": "status: locked"}],
    )

    assert "Editable.md" in result["updated"]
    assert any(s["path"] == "Locked.md" for s in result["skipped"])


# ------------------------------------------------------------------ #
# 9. Exception rules — path_glob
# ------------------------------------------------------------------ #

def test_exception_path_glob_skips_matching_paths(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Templates/Weekly", "OldTerm in template")
    write_note(svc, "Projects/Task", "OldTerm in project")

    result = svc.str_replace_vault(
        "OldTerm", "NewTerm",
        dry_run=True,
        exception_rules=[{"type": "path_glob", "value": "Templates"}],
    )

    assert "Projects/Task.md" in result["updated"]
    assert any(s["path"] == "Templates/Weekly.md" for s in result["skipped"])


# ------------------------------------------------------------------ #
# 10. Exception rules — contains_string
# ------------------------------------------------------------------ #

def test_exception_contains_string_skips_sentinel_notes(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Safe", "OldTerm here\nDO NOT EDIT")
    write_note(svc, "Normal", "OldTerm here")

    result = svc.str_replace_vault(
        "OldTerm", "NewTerm",
        dry_run=True,
        exception_rules=[{"type": "contains_string", "value": "DO NOT EDIT"}],
    )

    assert "Normal.md" in result["updated"]
    assert any(s["path"] == "Safe.md" for s in result["skipped"])


# ------------------------------------------------------------------ #
# 11. Multiple exception rules — OR logic
# ------------------------------------------------------------------ #

def test_multiple_exception_rules_any_match_skips(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Archive/Note", "OldTerm")          # matches folder rule
    write_note(svc, "Live/Tagged", "OldTerm #frozen")   # matches tag rule
    write_note(svc, "Live/Normal", "OldTerm")           # matches neither

    result = svc.str_replace_vault(
        "OldTerm", "NewTerm",
        dry_run=True,
        exception_rules=[
            {"type": "folder", "value": "Archive"},
            {"type": "tag",    "value": "#frozen"},
        ],
    )

    skipped_paths = {s["path"] for s in result["skipped"]}
    assert "Archive/Note.md" in skipped_paths
    assert "Live/Tagged.md" in skipped_paths
    assert "Live/Normal.md" in result["updated"]


# ------------------------------------------------------------------ #
# 12. Ambiguous — multiple occurrences, require_unique_per_note=True
# ------------------------------------------------------------------ #

def test_ambiguous_note_is_skipped_when_unique_required(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Note", "OldTerm here and OldTerm there")

    result = svc.str_replace_vault("OldTerm", "NewTerm", dry_run=True)

    assert "Note.md" in result["ambiguous"]
    assert "Note.md" not in result["updated"]


def test_ambiguous_note_replaced_when_unique_not_required(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Note", "OldTerm here and OldTerm there")

    result = svc.str_replace_vault(
        "OldTerm", "NewTerm",
        dry_run=False,
        require_unique_per_note=False,
    )

    assert "Note.md" in result["updated"]
    content = (tmp_path / "Note.md").read_text(encoding="utf-8")
    assert "OldTerm" not in content
    assert content.count("NewTerm") == 2


# ------------------------------------------------------------------ #
# 13. path_glob scoping
# ------------------------------------------------------------------ #

def test_path_glob_limits_scope(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Projects/Task", "OldTerm")
    write_note(svc, "Inbox/Idea", "OldTerm")

    result = svc.str_replace_vault(
        "OldTerm", "NewTerm",
        dry_run=True,
        path_glob="Projects/",
    )

    assert "Projects/Task.md" in result["updated"]
    assert "Inbox/Idea.md" not in result["updated"]
    # Inbox note is outside scope — not in updated, skipped, or ambiguous.
    skipped_paths = {s["path"] for s in result["skipped"]}
    assert "Inbox/Idea.md" not in skipped_paths


# ------------------------------------------------------------------ #
# 14. Unchanged count
# ------------------------------------------------------------------ #

def test_unchanged_count_reflects_notes_with_no_match(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "HasIt", "OldTerm here")
    write_note(svc, "NoMatch1", "unrelated content")
    write_note(svc, "NoMatch2", "also unrelated")

    result = svc.str_replace_vault("OldTerm", "NewTerm", dry_run=True)

    assert result["unchanged_count"] == 2
    assert len(result["updated"]) == 1


# ------------------------------------------------------------------ #
# 15. No match anywhere — graceful empty result
# ------------------------------------------------------------------ #

def test_no_match_returns_empty_updated(tmp_path: Path) -> None:
    svc = make_service(tmp_path)
    write_note(svc, "Note", "nothing interesting here")

    result = svc.str_replace_vault("TermThatDoesNotExist", "X", dry_run=True)

    assert result["updated"] == []
    assert result["skipped"] == []
    assert result["ambiguous"] == []
    assert result["unchanged_count"] == 1
