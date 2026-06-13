"""High-level knowledge-management operations for Obsidian vaults."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from obsidian_mcp.knowledge.analysis import (
    NoteDocument,
    build_dataview_dashboard,
    build_relationship_graph as build_graph,
    classify_para,
    detect_duplicate_notes,
    generate_excalidraw_markdown,
    parse_johnny_decimal_prefix,
    semantic_rank,
    suggest_tags,
)
from obsidian_mcp.vault.service import VaultService

HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


class KnowledgeService:
    """Advanced local knowledge operations built on `VaultService`."""

    def __init__(self, vault: VaultService) -> None:
        self.vault = vault

    def build_moc(self, topic: str, output_path: str | None = None, limit: int = 20) -> dict[str, Any]:
        """Build a map-of-content note for a topic."""
        documents = self._documents()
        related = semantic_rank(topic, documents, limit=limit)
        lines = [f"# {topic} MOC", "", "## Related Notes"]
        for result in related:
            note_stem = Path(result["path"]).with_suffix("").as_posix()
            lines.append(f"- [[{note_stem}]] - score {result['score']}")
        content = "\n".join(lines) + "\n"
        path = output_path or f"MOCs/{topic}"
        return self.vault.create_note(path, content)

    def create_atomic_note(
        self,
        path: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        aliases: list[str] | None = None,
        source_links: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a focused atomic note with frontmatter and source links."""
        note_tags = tags or []
        note_aliases = aliases or []
        links = source_links or []
        frontmatter = [
            "---",
            f"title: {title}",
            "aliases:",
            *[f"  - {alias}" for alias in note_aliases],
            "tags:",
            *[f"  - {tag}" for tag in note_tags],
            "---",
            "",
            f"# {title}",
            "",
            content,
        ]
        if links:
            frontmatter.extend(["", "## Sources", *[f"- [[{link}]]" for link in links]])
        return self.vault.create_note(path, "\n".join(frontmatter) + "\n")

    def refactor_large_note(self, path: str, create_notes: bool = False) -> dict[str, Any]:
        """Return heading-based split proposals and optionally create child notes."""
        source = self.vault.read_note(path)
        content = source["content"]
        headings = list(HEADING_PATTERN.finditer(content))
        proposals: list[dict[str, Any]] = []
        for index, match in enumerate(headings):
            start = match.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
            title = match.group(1).strip()
            child_path = f"{Path(source['path']).with_suffix('').as_posix()}/{title}"
            proposal = {"title": title, "path": f"{child_path}.md", "content": content[start:end].strip()}
            if create_notes:
                self.create_atomic_note(child_path, title, proposal["content"], source_links=[source["path"]])
            proposals.append(proposal)
        return {"source": source["path"], "proposals": proposals}

    def suggest_backlinks(self, path: str, limit: int = 10) -> list[dict[str, Any]]:
        """Suggest candidate backlinks for a note."""
        source = self._document_from_payload(self.vault.read_note(path))
        existing = set(self.vault.find_backlinks(path))
        candidates = [doc for doc in self._documents() if doc.path != source.path and doc.path not in existing]
        return semantic_rank(source.searchable_text(), candidates, limit=limit)

    def auto_tag(self, path: str, limit: int = 5) -> list[dict[str, Any]]:
        """Suggest tags for a note from existing vault tags and content terms."""
        source = self._document_from_payload(self.vault.read_note(path))
        existing_tags = sorted({tag for doc in self._documents() for tag in doc.tags})
        return suggest_tags(source, existing_tags, limit=limit)

    def semantic_search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Run deterministic local semantic-style search."""
        return semantic_rank(query, self._documents(), limit=limit)

    def detect_duplicates(self, threshold: float = 82) -> list[dict[str, Any]]:
        """Detect likely duplicate notes."""
        return detect_duplicate_notes(self._documents(), threshold=threshold)

    def build_relationship_graph(self) -> dict[str, list[dict[str, Any]]]:
        """Build a relationship graph across markdown notes."""
        return build_graph(self._documents())

    def suggest_para_location(self, path: str) -> dict[str, str]:
        """Suggest a PARA bucket and folder for a note."""
        document = self._document_from_payload(self.vault.read_note(path))
        bucket = classify_para(document)
        return {"path": document.path, "bucket": bucket, "folder": bucket}

    def suggest_johnny_decimal_location(self, path: str) -> dict[str, str | None]:
        """Return Johnny Decimal prefixes detected for a note path."""
        document = self._document_from_payload(self.vault.read_note(path))
        parsed = parse_johnny_decimal_prefix(document.path)
        parsed["path"] = document.path
        return parsed

    def create_dataview_dashboard(
        self,
        path: str,
        title: str,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a Dataview-compatible dashboard note."""
        dashboard_tags = tags if tags is not None else sorted({tag for doc in self._documents() for tag in doc.tags})
        return self.vault.create_note(path, build_dataview_dashboard(title, dashboard_tags))

    def generate_excalidraw_architecture(self, path: str, title: str = "Architecture") -> dict[str, Any]:
        """Create an Excalidraw architecture note from the relationship graph."""
        output_path = path if path.endswith(".excalidraw.md") else f"{path}.excalidraw.md"
        return self.vault.create_note(
            output_path,
            generate_excalidraw_markdown(title, self.build_relationship_graph()),
        )

    def _documents(self) -> list[NoteDocument]:
        documents: list[NoteDocument] = []
        for file_path in self.vault.list_files():
            if file_path.endswith(".md"):
                documents.append(self._document_from_payload(self.vault.read_note(file_path)))
        return documents

    @staticmethod
    def _document_from_payload(payload: dict[str, Any]) -> NoteDocument:
        metadata = payload["metadata"]
        title = metadata.get("title") or _first_heading(payload["content"]) or Path(payload["path"]).stem
        return NoteDocument(
            path=payload["path"],
            title=title,
            content=payload["content"],
            tags=list(metadata.get("tags", [])),
            aliases=list(metadata.get("aliases", [])),
            links=list(metadata.get("wikilinks", [])) + list(metadata.get("markdown_links", [])),
        )


def _first_heading(content: str) -> str | None:
    for line in content.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return None
