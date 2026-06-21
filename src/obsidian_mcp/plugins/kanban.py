"""KanbanService – generate and manage Obsidian Kanban-plugin boards.

The Kanban plugin (mgmeyers/obsidian-kanban) stores an entire board in a
single markdown file:

    ---
    kanban-plugin: basic
    ---

    ## To Do

    - [ ] Card text
    - [ ] Another card 📅 2026-07-01 🔼

    ## In Progress

    - [ ] Card in progress

    ## Done

    **Complete**
    - [x] Finished card

Format rules (load-bearing — the plugin is strict about these):
  - Frontmatter MUST contain ``kanban-plugin: basic`` (or ``board``, which
    newer forks/forks-of-forks also recognise) for the file to render as
    a board instead of a plain note.
  - Each ``##`` heading is one lane (column), in document order — left to
    right on the board.
  - Cards are checkbox list items (``- [ ]`` / ``- [x]``) directly under
    a lane heading, exactly like a Tasks-plugin checkbox line. This means
    every Tasks emoji (📅 ⏳ 🛫 🔼 🔁 etc.) works on a Kanban card for free.
  - A lane intended to represent "done" conventionally starts with a
    bold ``**Complete**`` marker line before its cards — this is a Kanban
    plugin setting/convention, not a hard requirement, but a "Done" lane
    is recognised when this marker is present.
  - Cards can themselves be wikilinks ``- [ ] [[Some Note]]`` — Kanban
    renders the linked note's title as the card and keeps it navigable.

This service deliberately reuses TasksService's checkbox formatting so
cards stay 100% Tasks-plugin compatible — a card created here can be
picked up by ``tasks_aggregate`` / ``tasks_complete`` and vice versa.
"""

from __future__ import annotations

import re
from typing import Any

from obsidian_mcp.plugins.tasks import TasksService
from obsidian_mcp.vault.service import VaultService

_BOARD_MARKER = "kanban-plugin: basic"
_LANE_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_CARD_LINE_RE = re.compile(
    r"^[ \t]*[-*][ \t]+\[(?P<state>[ xX\-/])\][ \t]+(?P<text>.+)$",
    re.MULTILINE,
)
_COMPLETE_MARKER_RE = re.compile(r"^\*\*Complete\*\*\s*$", re.MULTILINE)


class KanbanService:
    """Create, read, and mutate Obsidian Kanban-plugin board notes."""

    def __init__(self, vault: VaultService) -> None:
        self._vault = vault
        # Reuse Tasks formatting so cards carry real Tasks-plugin syntax.
        self._tasks = TasksService(vault)

    # ------------------------------------------------------------------ #
    # Board creation
    # ------------------------------------------------------------------ #

    def create_board(
        self,
        path: str,
        title: str,
        lanes: list[dict[str, Any]],
        *,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a new Kanban board note.

        Parameters
        ----------
        path:
            Vault-relative output path. ``.md`` is appended if missing.
        title:
            Board title — stored in frontmatter, not rendered on the board
            itself (Kanban boards have no visible title heading).
        lanes:
            Ordered list of lane specs::

                {
                    "name": "To Do",
                    "is_done_lane": False,   # optional, default False
                    "cards": [
                        {
                            "text": "Set up homelab DNS",
                            "due": "2026-07-01",        # optional
                            "scheduled": None,           # optional
                            "priority": "high",          # optional
                            "recurrence": None,          # optional
                            "link": None,                # optional — wikilink target instead of plain text
                        },
                        ...
                    ],
                }

            Lane order in the list is left-to-right column order on the board.
        tags:
            Optional frontmatter tags for the board note itself.
        """
        output_path = path if path.endswith(".md") else f"{path}.md"
        content = self._render_board(title, lanes, tags=tags)
        return self._vault.create_note(output_path, content)

    def create_simple_board(
        self,
        path: str,
        title: str,
        lane_names: list[str],
        *,
        done_lane: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an empty board with just lane headings — no cards yet.

        Convenience wrapper around create_board for the common case of
        scaffolding a board structure before populating it.

        Parameters
        ----------
        lane_names:
            Lane titles in left-to-right order, e.g. ["Backlog", "In Progress", "Done"].
        done_lane:
            If given, must match one entry in lane_names exactly — that
            lane gets the **Complete** marker.
        """
        lanes = [
            {"name": name, "is_done_lane": (name == done_lane), "cards": []}
            for name in lane_names
        ]
        return self.create_board(path, title, lanes, tags=tags)

    # ------------------------------------------------------------------ #
    # Card mutation
    # ------------------------------------------------------------------ #

    def add_card(
        self,
        board_path: str,
        lane_name: str,
        text: str,
        *,
        due: str | None = None,
        scheduled: str | None = None,
        priority: str | None = None,
        recurrence: str | None = None,
        link: str | None = None,
    ) -> dict[str, Any]:
        """Add a new card to a lane. Creates the lane if it doesn't exist yet.

        New cards are appended to the bottom of the lane.
        """
        note = self._vault.read_note(board_path)
        content = note["content"]
        self._require_board(content, board_path)

        card_line = self._format_card(
            text, due=due, scheduled=scheduled, priority=priority,
            recurrence=recurrence, link=link,
        )
        new_content = _insert_card_in_lane(content, lane_name, card_line)
        self._vault.update_note(board_path, new_content)
        return {"board": board_path, "lane": lane_name, "card": card_line}

    def move_card(
        self,
        board_path: str,
        card_text_fragment: str,
        target_lane: str,
    ) -> dict[str, Any]:
        """Move the first card matching *card_text_fragment* to a different lane.

        Matching is a case-insensitive substring match against card text.
        Preserves the card's full line (dates, priority, links) on move.
        """
        note = self._vault.read_note(board_path)
        content = note["content"]
        self._require_board(content, board_path)

        lanes = _parse_lanes(content)
        moved_line: str | None = None

        for lane in lanes:
            for card in lane["cards"]:
                if card_text_fragment.lower() in card["text"].lower():
                    moved_line = card["raw"]
                    break
            if moved_line:
                break

        if moved_line is None:
            return {"board": board_path, "moved": False}

        # Remove from original lane, then insert into target lane
        content = _remove_card_line(content, moved_line)
        content = _insert_card_in_lane(content, target_lane, moved_line)
        self._vault.update_note(board_path, content)
        return {"board": board_path, "moved": True, "to_lane": target_lane, "card": moved_line}

    def complete_card(self, board_path: str, card_text_fragment: str) -> dict[str, Any]:
        """Mark a card's checkbox as done in place (does not move lanes).

        Use move_card afterwards if completed cards should move to a
        "Done" lane — Kanban does not do this automatically.
        """
        # Reuses TasksService's checkbox-completion logic — cards are
        # just Tasks-formatted checkbox lines.
        return self._tasks.complete_task(board_path, card_text_fragment)

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #

    def read_board(self, board_path: str) -> dict[str, Any]:
        """Parse a board into structured lanes and cards.

        Returns
        -------
        dict with keys:
            path  — board path
            lanes — list of {name, is_done_lane, cards: [{text, state, raw, ...}]}
        """
        note = self._vault.read_note(board_path)
        self._require_board(note["content"], board_path)
        return {"path": board_path, "lanes": _parse_lanes(note["content"])}

    def lane_summary(self, board_path: str) -> dict[str, int]:
        """Return a quick card-count-per-lane summary."""
        board = self.read_board(board_path)
        return {lane["name"]: len(lane["cards"]) for lane in board["lanes"]}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _format_card(
        self,
        text: str,
        *,
        due: str | None = None,
        scheduled: str | None = None,
        priority: str | None = None,
        recurrence: str | None = None,
        link: str | None = None,
    ) -> str:
        """Format one card line, optionally as a wikilink card."""
        body = f"[[{link}]]" if link else text.strip()
        # Reuse TasksService's emoji-formatting logic by formatting the
        # body through the same private helper, then swapping the prefix.
        formatted = self._tasks._format_task(
            body, due=due, scheduled=scheduled, priority=priority, recurrence=recurrence,
        )
        return formatted  # already "- [ ] ..." formatted

    @staticmethod
    def _require_board(content: str, path: str) -> None:
        if _BOARD_MARKER not in content and "kanban-plugin: board" not in content:
            raise ValueError(
                f"'{path}' is not a Kanban board (missing 'kanban-plugin' frontmatter key)."
            )

    def _render_board(
        self,
        title: str,
        lanes: list[dict[str, Any]],
        *,
        tags: list[str] | None = None,
    ) -> str:
        tag_list = tags or []
        lines = [
            "---",
            f"kanban-plugin: {_BOARD_MARKER.split(': ')[1]}",
            f"title: {title}",
        ]
        if tag_list:
            lines.append(f"tags: [{', '.join(tag_list)}]")
        lines += ["---", ""]

        for lane in lanes:
            lines.append(f"## {lane['name']}")
            lines.append("")
            if lane.get("is_done_lane"):
                lines.append("**Complete**")
            cards = lane.get("cards", [])
            for card in cards:
                if isinstance(card, str):
                    # Allow plain strings as a shorthand for simple cards
                    lines.append(f"- [ ] {card}")
                    continue
                lines.append(self._format_card(
                    card["text"],
                    due=card.get("due"),
                    scheduled=card.get("scheduled"),
                    priority=card.get("priority"),
                    recurrence=card.get("recurrence"),
                    link=card.get("link"),
                ))
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


# ── Module-level parsing helpers ───────────────────────────────────────

def _parse_lanes(content: str) -> list[dict[str, Any]]:
    """Split board content into lanes (## headings) and parse their cards."""
    headings = list(_LANE_RE.finditer(content))
    lanes: list[dict[str, Any]] = []

    for i, heading_match in enumerate(headings):
        name = heading_match.group(1).strip()
        start = heading_match.end()
        end = headings[i + 1].start() if i + 1 < len(headings) else len(content)
        lane_body = content[start:end]

        is_done_lane = bool(_COMPLETE_MARKER_RE.search(lane_body))
        cards = []
        for card_match in _CARD_LINE_RE.finditer(lane_body):
            cards.append({
                "text": card_match.group("text").strip(),
                "state": "done" if card_match.group("state") in ("x", "X") else "open",
                "raw": card_match.group(0).strip(),
            })

        lanes.append({"name": name, "is_done_lane": is_done_lane, "cards": cards})

    return lanes


def _insert_card_in_lane(content: str, lane_name: str, card_line: str) -> str:
    """Insert *card_line* at the bottom of *lane_name*'s card list.

    If the lane doesn't exist, it is created at the end of the board.
    """
    headings = list(_LANE_RE.finditer(content))
    target_idx = None
    for i, m in enumerate(headings):
        if m.group(1).strip() == lane_name:
            target_idx = i
            break

    if target_idx is None:
        # Lane doesn't exist — append a new lane at the end
        sep = "\n\n" if not content.endswith("\n\n") else ""
        return content + f"{sep}## {lane_name}\n\n{card_line}\n"

    start = headings[target_idx].end()
    end = headings[target_idx + 1].start() if target_idx + 1 < len(headings) else len(content)
    lane_body = content[start:end]

    # Insert before trailing whitespace of the lane body, after existing cards
    stripped = lane_body.rstrip("\n")
    new_lane_body = stripped + ("\n" if stripped.strip() else "") + card_line + "\n\n"

    return content[:start] + new_lane_body + content[end:]


def _remove_card_line(content: str, raw_card_line: str) -> str:
    """Remove the first occurrence of an exact card line from the board."""
    lines = content.split("\n")
    target = raw_card_line.strip()
    for i, line in enumerate(lines):
        if line.strip() == target:
            del lines[i]
            break
    return "\n".join(lines)
