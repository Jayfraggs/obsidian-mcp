"""Deterministic local analysis helpers for knowledge-management tools."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
import re
from typing import Any

from rapidfuzz import fuzz

STOP_WORDS = {
    "and",
    "are",
    "for",
    "from",
    "into",
    "the",
    "with",
    "your",
}
TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]+")
JOHNNY_AREA_PATTERN = re.compile(r"\b\d0-\d9\b")
JOHNNY_CATEGORY_PATTERN = re.compile(r"\b\d{2}\b")
JOHNNY_ITEM_PATTERN = re.compile(r"\b\d{2}\.\d{2}\b")


@dataclass(frozen=True)
class NoteDocument:
    """Normalized note data used by local analysis helpers."""

    path: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)

    def searchable_text(self) -> str:
        """Return text used for deterministic local scoring."""
        return " ".join([self.path, self.title, self.content, *self.tags, *self.aliases, *self.links])


def tokenize(text: str) -> list[str]:
    """Tokenize text into normalized non-noise terms."""
    tokens = [token.lower() for token in TOKEN_PATTERN.findall(text)]
    return [token for token in tokens if len(token) > 2 and token not in STOP_WORDS]


def semantic_rank(query: str, documents: list[NoteDocument], limit: int = 10) -> list[dict[str, Any]]:
    """Rank documents with deterministic token overlap and fuzzy scoring."""
    query_tokens = set(tokenize(query))
    results: list[dict[str, Any]] = []
    for document in documents:
        text = document.searchable_text()
        document_tokens = set(tokenize(text))
        overlap = len(query_tokens & document_tokens)
        overlap_score = (overlap / max(len(query_tokens), 1)) * 60
        fuzzy_score = fuzz.partial_ratio(query.lower(), text.lower()) * 0.4
        score = round(overlap_score + fuzzy_score, 2)
        results.append({"path": document.path, "title": document.title, "score": score})
    return sorted(results, key=lambda item: (-item["score"], item["path"]))[:limit]


def detect_duplicate_notes(
    documents: list[NoteDocument],
    threshold: float = 82,
) -> list[dict[str, Any]]:
    """Find likely duplicate notes using title and content similarity."""
    duplicates: list[dict[str, Any]] = []
    for index, first in enumerate(documents):
        for second in documents[index + 1 :]:
            title_score = fuzz.ratio(first.title.lower(), second.title.lower())
            content_score = fuzz.token_set_ratio(first.content.lower(), second.content.lower())
            score = round((title_score * 0.55) + (content_score * 0.45), 2)
            if score >= threshold:
                duplicates.append({"first": first.path, "second": second.path, "score": score})
    return sorted(duplicates, key=lambda item: (-item["score"], item["first"], item["second"]))


def classify_para(document: NoteDocument) -> str:
    """Classify a note into a PARA bucket."""
    text = document.searchable_text().lower()
    path_head = document.path.split("/", maxsplit=1)[0].lower()
    if path_head in {"projects", "areas", "resources", "archives"}:
        return path_head.title()
    if any(term in text for term in ("deadline", "milestone", "project", "deliverable")):
        return "Projects"
    if any(term in text for term in ("habit", "standard", "responsibility", "area")):
        return "Areas"
    if any(term in text for term in ("reference", "resource", "article", "book")):
        return "Resources"
    if any(term in text for term in ("archive", "completed", "inactive")):
        return "Archives"
    return "Resources"


def parse_johnny_decimal_prefix(path: str) -> dict[str, str | None]:
    """Parse Johnny Decimal area, category, and item prefixes from a path."""
    parts = path.replace("\\", "/").split("/")
    category = None
    for part in parts[1:]:
        category = _first_match(JOHNNY_CATEGORY_PATTERN, part)
        if category:
            break
    return {
        "area": _first_match(JOHNNY_AREA_PATTERN, path),
        "category": category,
        "item": _first_match(JOHNNY_ITEM_PATTERN, path),
    }


def suggest_tags(
    document: NoteDocument,
    existing_tags: list[str],
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Suggest tags from existing vault tags and prominent content terms."""
    tokens = Counter(tokenize(document.searchable_text()))
    suggestions: list[dict[str, Any]] = []
    for tag in sorted(set(existing_tags)):
        tag_tokens = tokenize(tag.replace("/", " "))
        score = sum(tokens[token] for token in tag_tokens) * 10
        if score > 0:
            suggestions.append({"tag": tag, "score": score})

    for token, count in tokens.most_common():
        if token not in {item["tag"] for item in suggestions}:
            suggestions.append({"tag": token, "score": count})

    return sorted(suggestions, key=lambda item: (-item["score"], item["tag"]))[:limit]


def build_relationship_graph(
    documents: list[NoteDocument],
    *,
    include_tag_edges: bool = False,
    max_tag_edges_per_note: int = 10,
) -> dict[str, list[dict[str, Any]]]:
    """Build a local relationship graph from links and (optionally) shared tags.

    Parameters
    ----------
    include_tag_edges:
        If True, also emit edges between notes that share a tag. Defaults
        to False — on a tag-heavy vault, shared-tag edges grow roughly
        quadratically with note count and can blow up the response past
        MCP/transport size limits (observed: 500 notes with ~4 shared
        tags each → 67k edges, 5+ MB JSON). Link edges from actual
        [[wikilinks]] are the meaningful graph in almost all cases;
        tag edges are a "nice to have" that doesn't scale.
    max_tag_edges_per_note:
        When include_tag_edges=True, caps how many tag-edges originate
        from any single note (the busiest shared tag wins ties last).
        Prevents one popular tag (e.g. #homelab) from single-handedly
        re-introducing the blowup this function exists to avoid.
    """
    nodes = [{"id": doc.path, "title": doc.title, "tags": doc.tags} for doc in documents]
    title_to_path = {doc.title: doc.path for doc in documents}
    stem_to_path = {doc.path.removesuffix(".md").split("/")[-1]: doc.path for doc in documents}
    all_paths = {doc.path for doc in documents}
    edges: list[dict[str, Any]] = []

    for doc in documents:
        for link in doc.links:
            target = title_to_path.get(link) or stem_to_path.get(link) or (
                f"{link}.md" if f"{link}.md" in all_paths else None
            )
            if target and target != doc.path:
                edges.append({"source": doc.path, "target": target, "type": "link"})

    if include_tag_edges:
        edges.extend(_build_tag_edges(documents, max_tag_edges_per_note))

    return {"nodes": nodes, "edges": _dedupe_edges(edges)}


def _build_tag_edges(
    documents: list[NoteDocument],
    max_tag_edges_per_note: int,
) -> list[dict[str, Any]]:
    """Generate shared-tag edges in O(N · avg_tags) instead of O(N²).

    Groups notes by tag first, then connects within each tag's bucket —
    mathematically equivalent to the pairwise comparison but without ever
    materialising the full N×N comparison space. Still bounded per-note
    via max_tag_edges_per_note since a single popular tag with hundreds
    of notes would otherwise produce a complete graph on its own.
    """
    tag_buckets: dict[str, list[str]] = {}
    for doc in documents:
        for tag in doc.tags:
            tag_buckets.setdefault(tag, []).append(doc.path)

    edge_count_per_note: dict[str, int] = {}
    edges: list[dict[str, Any]] = []

    for tag, paths in tag_buckets.items():
        if len(paths) < 2:
            continue
        # Cap bucket size: an enormous shared tag is not useful signal
        # and would otherwise dominate every note's edge budget.
        for i, source in enumerate(paths):
            if edge_count_per_note.get(source, 0) >= max_tag_edges_per_note:
                continue
            for target in paths[i + 1:]:
                if edge_count_per_note.get(source, 0) >= max_tag_edges_per_note:
                    break
                if edge_count_per_note.get(target, 0) >= max_tag_edges_per_note:
                    continue
                edges.append({"source": source, "target": target, "type": "tag", "tag": tag})
                edge_count_per_note[source] = edge_count_per_note.get(source, 0) + 1
                edge_count_per_note[target] = edge_count_per_note.get(target, 0) + 1

    return edges


def build_dataview_dashboard(title: str, tags: list[str]) -> str:
    """Generate Dataview-compatible dashboard markdown."""
    tag_filters = "\n".join(
        f'WHERE contains(file.tags, "#{tag}")\nSORT file.mtime DESC' for tag in tags
    )
    sections = [
        f"# {title} Dashboard",
        "## Recently Updated",
        "```dataview",
        "TABLE file.mtime AS Updated",
        "FROM \"\"",
        "SORT file.mtime DESC",
        "LIMIT 20",
        "```",
        "## Tasks",
        "```dataview",
        "TASK FROM \"\"",
        "WHERE !completed",
        "```",
    ]
    if tag_filters:
        sections.extend(["## Tags", "```dataview", tag_filters, "```"])
    return "\n".join(sections) + "\n"


def generate_excalidraw_markdown(title: str, graph: dict[str, list[dict[str, Any]]]) -> str:
    """Generate an Excalidraw-compatible markdown note for a relationship graph.

    Built with the shared scene engine so every node carries its title as a
    bound text label and every edge is a properly bound arrow (the previous
    implementation put text on the rectangle itself, which Excalidraw ignores).
    """
    from obsidian_mcp.plugins import excalidraw_scene as sc

    skeleton: list[dict[str, Any]] = []
    handles: dict[str, str] = {}
    for index, node in enumerate(graph.get("nodes", [])):
        handle = f"node{index}"
        handles[node["id"]] = handle
        skeleton.append({"id": handle, "type": "rectangle", "label": str(node.get("title") or node["id"]),
                         "backgroundColor": "#dbe9ff"})
    seen: set[tuple[str, str, str]] = set()
    for edge in graph.get("edges", []):
        src, dst = handles.get(edge["source"]), handles.get(edge["target"])
        if src is None or dst is None or src == dst:
            continue
        label = f"#{edge['tag']}" if edge.get("type") == "tag" and edge.get("tag") else ""
        key = (src, dst, label)
        if key in seen:
            continue
        seen.add(key)
        arrow: dict[str, Any] = {"type": "arrow", "start": src, "end": dst}
        if label:
            arrow["label"] = label
        skeleton.append(arrow)
    built = sc.build_elements(skeleton, direction="LR", origin=(60.0, 60.0))
    return sc.build_drawing_file(title, sc.scene_payload(built.elements))


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0) if match else None


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for edge in edges:
        key = json.dumps(edge, sort_keys=True)
        if key not in seen:
            seen.add(key)
            result.append(edge)
    return result
