"""TemplaterService – render and apply Templater-style templates.

The Templater plugin processes ``<% ... %>`` expressions inside notes.
This service handles:
  - Listing available templates from the configured templates folder
  - Rendering static substitutions (date, file title, frontmatter values)
  - Applying a template to create a new note
  - Registering custom template stubs for Claude to generate on demand

Dynamic JavaScript execution (``<%* ... %>``) is not evaluated server-side
— those blocks are preserved as-is so Templater in Obsidian can process
them when the note is opened.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from obsidian_mcp.vault.service import VaultService

# ── Pattern matching ──────────────────────────────────────────────────
_STATIC_TAG_RE = re.compile(r"<%[-_]?\s*(.*?)\s*[-_]?%>", re.DOTALL)

# Substitutions we can resolve at generation time
_STATIC_SUBSTITUTIONS: dict[str, str] = {
    "tp.date.now()": lambda: date.today().isoformat(),
    'tp.date.now("YYYY-MM-DD")': lambda: date.today().isoformat(),
    'tp.date.now("DD-MM-YYYY")': lambda: datetime.today().strftime("%d-%m-%Y"),
    'tp.date.now("MMMM Do, YYYY")': lambda: datetime.today().strftime("%B %-d, %Y"),
}

_TEMPLATES_FOLDER_DEFAULT = "Templates"


class TemplaterService:
    """Render and apply Templater templates."""

    def __init__(
        self,
        vault: VaultService,
        templates_folder: str = _TEMPLATES_FOLDER_DEFAULT,
    ) -> None:
        self._vault = vault
        self._templates_folder = templates_folder.rstrip("/")

    # ------------------------------------------------------------------ #
    # Template discovery
    # ------------------------------------------------------------------ #

    def list_templates(self) -> list[dict[str, str]]:
        """Return all notes inside the templates folder."""
        prefix = self._templates_folder + "/"
        templates: list[dict[str, str]] = []
        for path in self._vault.list_files():
            if path.startswith(prefix) and path.endswith(".md"):
                name = Path(path).stem
                templates.append({"path": path, "name": name})
        return sorted(templates, key=lambda t: t["name"])

    def read_template(self, name_or_path: str) -> dict[str, Any]:
        """Return the raw content of a template by name or path."""
        path = self._resolve_template_path(name_or_path)
        return self._vault.read_note(path)

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def render(
        self,
        name_or_path: str,
        variables: dict[str, str] | None = None,
        *,
        title: str | None = None,
    ) -> str:
        """Render a template, substituting all resolvable static tags.

        Parameters
        ----------
        variables:
            Custom ``{key: value}`` map resolved as ``<% key %>`` and
            as ``{{key}}`` (double-brace convenience syntax).
        title:
            Used to resolve ``tp.file.title``.  Falls back to the
            template stem when not provided.
        """
        path = self._resolve_template_path(name_or_path)
        note = self._vault.read_note(path)
        content = note["content"]
        return self._substitute(content, variables=variables or {}, title=title or Path(path).stem)

    def render_string(
        self,
        template_content: str,
        variables: dict[str, str] | None = None,
        *,
        title: str | None = None,
    ) -> str:
        """Render a raw template string (no vault lookup needed)."""
        return self._substitute(template_content, variables=variables or {}, title=title or "Untitled")

    # ------------------------------------------------------------------ #
    # Apply template → create note
    # ------------------------------------------------------------------ #

    def apply_template(
        self,
        template_name_or_path: str,
        output_path: str,
        *,
        variables: dict[str, str] | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Render a template and save it as a new note.

        Parameters
        ----------
        output_path:
            Vault-relative destination path (without ``.md`` is fine).
        variables:
            Custom substitution map passed to :meth:`render`.
        title:
            Resolves ``tp.file.title`` and becomes the note's H1 title
            when the template contains ``# <% tp.file.title %>``.
        """
        effective_title = title or Path(output_path).stem
        rendered = self.render(template_name_or_path, variables, title=effective_title)
        return self._vault.create_note(output_path, rendered)

    # ------------------------------------------------------------------ #
    # Template creation / scaffolding
    # ------------------------------------------------------------------ #

    def create_template(
        self,
        name: str,
        template_type: str,
        *,
        custom_fields: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a best-practice Templater template note.

        Parameters
        ----------
        name:
            Template name (becomes the file stem).
        template_type:
            One of ``concept``, ``project``, ``journal``, ``reference``,
            ``meeting``, ``person``, ``system``.
        custom_fields:
            Additional frontmatter field names to include.
        tags:
            Frontmatter tags baked into the template.
        """
        scaffold = _SCAFFOLDS.get(template_type, _SCAFFOLDS["concept"])
        content = scaffold(name=name, custom_fields=custom_fields or [], tags=tags or [])
        path = f"{self._templates_folder}/{name}"
        return self._vault.create_note(path, content)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _resolve_template_path(self, name_or_path: str) -> str:
        if name_or_path.endswith(".md") or "/" in name_or_path:
            return name_or_path
        return f"{self._templates_folder}/{name_or_path}"

    def _substitute(
        self,
        content: str,
        *,
        variables: dict[str, str],
        title: str,
    ) -> str:
        today = date.today().isoformat()

        def _replace(m: re.Match) -> str:
            expr = m.group(1).strip()

            # Dynamic JS block — preserve as-is for Templater to handle
            if expr.startswith("*"):
                return m.group(0)

            # Resolvable statics
            if expr in _STATIC_SUBSTITUTIONS:
                result = _STATIC_SUBSTITUTIONS[expr]
                return result() if callable(result) else result

            if expr == "tp.file.title":
                return title
            if expr in ("tp.date.now()", 'tp.date.now("YYYY-MM-DD")'):
                return today

            # Custom variables (both <%key%> and {{key}} style)
            if expr in variables:
                return variables[expr]

            # Unknown → preserve
            return m.group(0)

        content = _STATIC_TAG_RE.sub(_replace, content)

        # Double-brace variables: {{key}}
        for key, val in variables.items():
            content = content.replace("{{" + key + "}}", val)

        return content


# ── Template scaffolds ─────────────────────────────────────────────────

def _concept_scaffold(*, name: str, custom_fields: list[str], tags: list[str]) -> str:
    tag_str = "[" + ", ".join(tags) + "]" if tags else "[]"
    extra = "\n".join(f"{f}: " for f in custom_fields)
    return (
        "---\n"
        "title: <% tp.file.title %>\n"
        "type: concept\n"
        f"tags: {tag_str}\n"
        "created: <% tp.date.now(\"YYYY-MM-DD\") %>\n"
        "updated: <% tp.date.now(\"YYYY-MM-DD\") %>\n"
        "status: seed\n"
        + (extra + "\n" if extra else "")
        + "---\n\n"
        "# <% tp.file.title %>\n\n"
        "## Summary\n\n\n\n"
        "## Key Points\n\n- \n\n"
        "## Deep Dive\n\n\n\n"
        "## Connections\n\n- [[Related Note]]\n\n"
        "## Questions / Gaps\n\n- \n"
    )


def _project_scaffold(*, name: str, custom_fields: list[str], tags: list[str]) -> str:
    tag_str = "[" + ", ".join(tags) + "]" if tags else "[]"
    extra = "\n".join(f"{f}: " for f in custom_fields)
    return (
        "---\n"
        "title: <% tp.file.title %>\n"
        "type: project\n"
        f"tags: {tag_str}\n"
        "created: <% tp.date.now(\"YYYY-MM-DD\") %>\n"
        "status: active\n"
        "area: \n"
        "priority:: medium\n"
        + (extra + "\n" if extra else "")
        + "---\n\n"
        "# <% tp.file.title %>\n\n"
        "## Goal\n\n\n\n"
        "## Tasks\n\n"
        "- [ ] First task 📅 <% tp.date.now(\"YYYY-MM-DD\") %>\n\n"
        "## Notes\n\n\n\n"
        "## Resources\n\n- \n\n"
        "## Log\n\n### <% tp.date.now(\"YYYY-MM-DD\") %>\n\n\n"
    )


def _journal_scaffold(*, name: str, custom_fields: list[str], tags: list[str]) -> str:
    tag_str = "[journal, " + ", ".join(tags) + "]" if tags else "[journal]"
    return (
        "---\n"
        "title: <% tp.date.now(\"YYYY-MM-DD\") %>\n"
        "type: journal\n"
        f"tags: {tag_str}\n"
        "date: <% tp.date.now(\"YYYY-MM-DD\") %>\n"
        "mood: \n"
        "---\n\n"
        "# <% tp.date.now(\"MMMM Do, YYYY\") %>\n\n"
        "## Today's focus\n\n\n\n"
        "## Tasks\n\n"
        "- [ ] \n\n"
        "## Notes\n\n\n\n"
        "## Reflection\n\n\n"
    )


def _meeting_scaffold(*, name: str, custom_fields: list[str], tags: list[str]) -> str:
    tag_str = "[meeting, " + ", ".join(tags) + "]" if tags else "[meeting]"
    return (
        "---\n"
        "title: <% tp.file.title %>\n"
        "type: meeting\n"
        f"tags: {tag_str}\n"
        "date: <% tp.date.now(\"YYYY-MM-DD\") %>\n"
        "attendees: []\n"
        "---\n\n"
        "# <% tp.file.title %>\n\n"
        "**Date:** <% tp.date.now(\"YYYY-MM-DD\") %>  \n"
        "**Attendees:** \n\n"
        "## Agenda\n\n1. \n\n"
        "## Notes\n\n\n\n"
        "## Action items\n\n"
        "- [ ] \n\n"
        "## Decisions\n\n- \n"
    )


def _reference_scaffold(*, name: str, custom_fields: list[str], tags: list[str]) -> str:
    tag_str = "[reference, " + ", ".join(tags) + "]" if tags else "[reference]"
    extra = "\n".join(f"{f}: " for f in custom_fields)
    return (
        "---\n"
        "title: <% tp.file.title %>\n"
        "type: reference\n"
        f"tags: {tag_str}\n"
        "created: <% tp.date.now(\"YYYY-MM-DD\") %>\n"
        "source: \n"
        "author: \n"
        + (extra + "\n" if extra else "")
        + "---\n\n"
        "# <% tp.file.title %>\n\n"
        "## Overview\n\n\n\n"
        "## Key Points\n\n- \n\n"
        "## Implementation\n\n\n\n"
        "## Troubleshooting\n\n\n\n"
        "## See Also\n\n- \n"
    )


def _system_scaffold(*, name: str, custom_fields: list[str], tags: list[str]) -> str:
    tag_str = "[system, " + ", ".join(tags) + "]" if tags else "[system]"
    return (
        "---\n"
        "title: <% tp.file.title %>\n"
        "type: system\n"
        f"tags: {tag_str}\n"
        "created: <% tp.date.now(\"YYYY-MM-DD\") %>\n"
        "status: active\n"
        "---\n\n"
        "# <% tp.file.title %>\n\n"
        "## Architecture\n\n\n\n"
        "## Components\n\n- \n\n"
        "## Configuration\n\n```yaml\n\n```\n\n"
        "## Troubleshooting\n\n\n\n"
        "## Connections\n\n- \n"
    )


_SCAFFOLDS: dict[str, Any] = {
    "concept": _concept_scaffold,
    "project": _project_scaffold,
    "journal": _journal_scaffold,
    "meeting": _meeting_scaffold,
    "reference": _reference_scaffold,
    "system": _system_scaffold,
}
