"""TasksService – create and manage Obsidian Tasks plugin formatted tasks.

The Tasks plugin understands a specific emoji-based syntax on checkbox lines:
    - [ ] Task description 📅 2026-06-15 🔼 🔁 every week

This service generates, parses, and aggregates tasks across the vault.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from obsidian_mcp.vault.service import VaultService

# ── Emoji tokens the Tasks plugin recognises ──────────────────────────
_DUE_EMOJI = "📅"
_SCHEDULED_EMOJI = "⏳"
_START_EMOJI = "🛫"
_DONE_EMOJI = "✅"
_CANCELLED_EMOJI = "❌"
_RECUR_EMOJI = "🔁"

_PRIORITY_EMOJI: dict[str, str] = {
    "highest": "⏫",
    "high": "🔼",
    "low": "🔽",
    "lowest": "⏬",
}
_EMOJI_TO_PRIORITY = {v: k for k, v in _PRIORITY_EMOJI.items()}

_TASK_LINE_RE = re.compile(
    r"^(?P<indent>[ \t]*)[-*][ \t]+\[(?P<state>[ xX\-/])\][ \t]+(?P<text>.+)$",
    re.MULTILINE,
)
_DUE_RE = re.compile(r"📅\s*(\d{4}-\d{2}-\d{2})")
_SCHEDULED_RE = re.compile(r"⏳\s*(\d{4}-\d{2}-\d{2})")
_DONE_RE = re.compile(r"✅\s*(\d{4}-\d{2}-\d{2})")
_RECUR_RE = re.compile(r"🔁\s*([^📅⏳🛫✅❌\n]+)")
_PRIORITY_RE = re.compile(r"[⏫🔼🔽⏬]")

_STATE_MAP = {" ": "open", "x": "done", "X": "done", "-": "cancelled", "/": "in_progress"}


class TasksService:
    """Create, parse, and aggregate Tasks-plugin formatted tasks."""

    def __init__(self, vault: VaultService) -> None:
        self._vault = vault

    # ------------------------------------------------------------------ #
    # Task creation
    # ------------------------------------------------------------------ #

    def create_task(
        self,
        note_path: str,
        text: str,
        *,
        due: str | None = None,
        scheduled: str | None = None,
        priority: str | None = None,
        recurrence: str | None = None,
        section: str | None = None,
    ) -> dict[str, Any]:
        """Append a new Tasks-formatted task to an existing note.

        Parameters
        ----------
        text:
            The task description (plain text, no leading ``- [ ]``).
        due:
            ISO date string ``YYYY-MM-DD``.
        scheduled:
            ISO date string for the scheduled date.
        priority:
            One of ``highest``, ``high``, ``low``, ``lowest``.
        recurrence:
            Recurrence string, e.g. ``every week``, ``every month``.
        section:
            Heading text to insert the task under (created if absent).
        """
        line = self._format_task(text, due=due, scheduled=scheduled,
                                 priority=priority, recurrence=recurrence)

        note = self._vault.read_note(note_path)
        content = note["content"]

        if section:
            content = _insert_under_heading(content, section, line)
        else:
            separator = "\n" if content.endswith("\n") else "\n\n"
            content = content + separator + line + "\n"

        self._vault.update_note(note_path, content)
        return {"note": note_path, "task": line}

    def create_task_note(
        self,
        path: str,
        title: str,
        tasks: list[dict[str, Any]],
        *,
        tags: list[str] | None = None,
        area: str | None = None,
    ) -> dict[str, Any]:
        """Create a dedicated task note with a list of tasks and a Dataview block.

        Each item in *tasks* is a dict with keys matching ``create_task``
        parameters (``text`` required; rest optional).
        """
        tag_list = tags or []
        frontmatter_lines = [
            "---",
            f"title: {title}",
            f"type: tasks",
            f"tags: [{', '.join(tag_list)}]",
        ]
        if area:
            frontmatter_lines.append(f"area: {area}")
        frontmatter_lines += ["status: active", "---", ""]

        task_lines = [f"# {title}", ""]
        for t in tasks:
            task_lines.append(
                self._format_task(
                    t["text"],
                    due=t.get("due"),
                    scheduled=t.get("scheduled"),
                    priority=t.get("priority"),
                    recurrence=t.get("recurrence"),
                )
            )

        task_lines += [
            "",
            "## Overview",
            "",
            "```dataview",
            "TASK",
            f'FROM "{path}"',
            "WHERE !completed",
            "SORT due ASC",
            "```",
        ]

        content = "\n".join(frontmatter_lines + task_lines) + "\n"
        return self._vault.create_note(path, content)

    # ------------------------------------------------------------------ #
    # Task parsing
    # ------------------------------------------------------------------ #

    def list_tasks(
        self,
        note_path: str,
        *,
        state: str | None = None,
    ) -> list[dict[str, Any]]:
        """Parse and return all tasks in a note.

        Parameters
        ----------
        state:
            Filter by state: ``open``, ``done``, ``cancelled``, ``in_progress``.
        """
        note = self._vault.read_note(note_path)
        tasks = _parse_tasks(note["content"], note["path"])
        if state:
            tasks = [t for t in tasks if t["state"] == state]
        return tasks

    def aggregate_tasks(
        self,
        *,
        state: str | None = "open",
        folder: str | None = None,
        due_before: str | None = None,
        priority: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Collect tasks across the entire vault (or a folder).

        Parameters
        ----------
        state:
            ``open`` | ``done`` | ``cancelled`` | ``in_progress`` | None for all.
        folder:
            Restrict to notes inside this vault-relative folder path.
        due_before:
            ISO date — return only tasks due on or before this date.
        priority:
            ``highest`` | ``high`` | ``low`` | ``lowest`` | None for all.
        """
        all_notes = self._vault.list_files()
        if folder:
            folder_prefix = folder.rstrip("/") + "/"
            all_notes = [p for p in all_notes if p.startswith(folder_prefix)]

        results: list[dict[str, Any]] = []
        cutoff = date.fromisoformat(due_before) if due_before else None

        for note_path in all_notes:
            if not note_path.endswith(".md"):
                continue
            note = self._vault.read_note(note_path)
            for task in _parse_tasks(note["content"], note_path):
                if state and task["state"] != state:
                    continue
                if priority and task.get("priority") != priority:
                    continue
                if cutoff and task.get("due"):
                    task_due = date.fromisoformat(task["due"])
                    if task_due > cutoff:
                        continue
                results.append(task)
                if len(results) >= limit:
                    return results

        return results

    def complete_task(self, note_path: str, task_text_fragment: str) -> dict[str, Any]:
        """Mark the first matching open task as done.

        Matches by substring of the task description.
        Appends the done emoji and today's date.
        """
        note = self._vault.read_note(note_path)
        content = note["content"]
        today = date.today().isoformat()

        def _replace(m: re.Match) -> str:
            if m.group("state") != " ":
                return m.group(0)
            if task_text_fragment.lower() not in m.group("text").lower():
                return m.group(0)
            return m.group(0).replace("[ ]", "[x]", 1) + f" {_DONE_EMOJI} {today}"

        new_content, count = _TASK_LINE_RE.subn(_replace, content)
        if count == 0:
            return {"note": note_path, "matched": False}
        self._vault.update_note(note_path, new_content)
        return {"note": note_path, "matched": True, "completed_on": today}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _format_task(
        text: str,
        *,
        due: str | None = None,
        scheduled: str | None = None,
        priority: str | None = None,
        recurrence: str | None = None,
    ) -> str:
        parts = [f"- [ ] {text.strip()}"]
        if recurrence:
            parts.append(f"{_RECUR_EMOJI} {recurrence}")
        if scheduled:
            parts.append(f"{_SCHEDULED_EMOJI} {scheduled}")
        if due:
            parts.append(f"{_DUE_EMOJI} {due}")
        if priority and priority in _PRIORITY_EMOJI:
            parts.append(_PRIORITY_EMOJI[priority])
        return " ".join(parts)


# ── Module-level helpers ───────────────────────────────────────────────

def _parse_tasks(content: str, source_path: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for m in _TASK_LINE_RE.finditer(content):
        raw_text = m.group("text")
        due_m = _DUE_RE.search(raw_text)
        sched_m = _SCHEDULED_RE.search(raw_text)
        done_m = _DONE_RE.search(raw_text)
        recur_m = _RECUR_RE.search(raw_text)
        priority_m = _PRIORITY_RE.search(raw_text)

        clean_text = _PRIORITY_RE.sub("", raw_text)
        for pat in (_DUE_RE, _SCHEDULED_RE, _DONE_RE, _RECUR_RE):
            clean_text = pat.sub("", clean_text).strip()

        tasks.append({
            "source": source_path,
            "state": _STATE_MAP.get(m.group("state"), "open"),
            "text": clean_text.strip(),
            "due": due_m.group(1) if due_m else None,
            "scheduled": sched_m.group(1) if sched_m else None,
            "done_on": done_m.group(1) if done_m else None,
            "recurrence": recur_m.group(1).strip() if recur_m else None,
            "priority": _EMOJI_TO_PRIORITY.get(priority_m.group(0)) if priority_m else None,
            "raw": m.group(0),
        })
    return tasks


def _insert_under_heading(content: str, heading: str, task_line: str) -> str:
    """Insert a task line under a specific heading.  Creates the heading if absent."""
    heading_re = re.compile(rf"^#+\s+{re.escape(heading)}\s*$", re.MULTILINE)
    m = heading_re.search(content)
    if m:
        insert_at = m.end()
        # Skip blank lines immediately after the heading
        while insert_at < len(content) and content[insert_at] in ("\n", "\r"):
            insert_at += 1
        return content[:insert_at] + task_line + "\n" + content[insert_at:]
    # Heading not found — append heading + task at end
    sep = "\n\n" if not content.endswith("\n\n") else ""
    return content + sep + f"## {heading}\n\n{task_line}\n"
