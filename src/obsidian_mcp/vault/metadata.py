"""Metadata extraction for Obsidian markdown notes."""

from dataclasses import dataclass
import re
from typing import Any

import frontmatter

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
INLINE_TAG_PATTERN = re.compile(r"(?<!\w)#([A-Za-z0-9_/-]+)")
TASK_PATTERN = re.compile(r"^\s*[-*]\s+\[[ xX]\]\s+.+$", re.MULTILINE)
DATAVIEW_FIELD_PATTERN = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_-]*)::\s*(.+?)\s*$", re.MULTILINE)
TEMPLATER_PATTERN = re.compile(r"<%[\s\S]*?%>")


@dataclass(frozen=True)
class NoteMetadata:
    """Extracted metadata for an Obsidian note."""

    path: str
    title: str | None
    aliases: list[str]
    tags: list[str]
    wikilinks: list[str]
    markdown_links: list[str]
    task_count: int
    dataview_fields: dict[str, str]
    has_templater: bool
    is_excalidraw: bool

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable metadata dictionary."""
        return {
            "path": self.path,
            "title": self.title,
            "aliases": self.aliases,
            "tags": self.tags,
            "wikilinks": self.wikilinks,
            "markdown_links": self.markdown_links,
            "task_count": self.task_count,
            "dataview_fields": self.dataview_fields,
            "has_templater": self.has_templater,
            "is_excalidraw": self.is_excalidraw,
        }


def extract_note_metadata(path: str, content: str) -> NoteMetadata:
    """Extract Obsidian-compatible metadata from markdown content."""
    parsed = frontmatter.loads(content)
    body = parsed.content
    frontmatter_tags = _coerce_string_list(parsed.metadata.get("tags"))
    frontmatter_aliases = _coerce_string_list(parsed.metadata.get("aliases"))
    inline_tags = INLINE_TAG_PATTERN.findall(body)
    tags = sorted(set(frontmatter_tags + inline_tags))

    return NoteMetadata(
        path=path,
        title=_coerce_optional_string(parsed.metadata.get("title")),
        aliases=frontmatter_aliases,
        tags=tags,
        wikilinks=_dedupe_preserve_order(WIKILINK_PATTERN.findall(body)),
        markdown_links=_dedupe_preserve_order(MARKDOWN_LINK_PATTERN.findall(body)),
        task_count=len(TASK_PATTERN.findall(body)),
        dataview_fields=dict(sorted(DATAVIEW_FIELD_PATTERN.findall(body))),
        has_templater=bool(TEMPLATER_PATTERN.search(body)),
        is_excalidraw=_is_excalidraw(path, parsed.metadata),
    )


def _coerce_optional_string(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _coerce_string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _is_excalidraw(path: str, metadata: dict[str, Any]) -> bool:
    return path.endswith(".excalidraw.md") or "excalidraw-plugin" in metadata
