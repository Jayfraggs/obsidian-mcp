"""OmnisearchService – optimise notes for Omnisearch discoverability.

Omnisearch indexes note content, frontmatter, and file paths.  This
service analyses notes and suggests improvements that make them surface
reliably when searched from Claude Desktop or Obsidian's quick-switcher.

No Omnisearch plugin installation is required — everything is static
frontmatter and content analysis.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from obsidian_mcp.knowledge.analysis import tokenize
from obsidian_mcp.vault.service import VaultService

_ALIAS_MAX = 8
_KEYWORD_MAX = 10
_MIN_TOKEN_FREQ = 2   # term must appear at least this often to be suggested


class OmnisearchService:
    """Analyse notes and generate Omnisearch-friendly metadata."""

    def __init__(self, vault: VaultService) -> None:
        self._vault = vault

    # ------------------------------------------------------------------ #
    # Per-note optimisation
    # ------------------------------------------------------------------ #

    def suggest_aliases(self, path: str, limit: int = 5) -> dict[str, Any]:
        """Suggest additional frontmatter aliases for a note.

        Aliases are generated from:
        - Title variations (abbreviations, acronyms, common spellings)
        - Prominent noun phrases in the note body
        - Existing wikilink labels pointing to this note
        """
        note = self._vault.read_note(path)
        metadata = note["metadata"]
        title: str = metadata.get("title") or Path(path).stem
        existing: list[str] = list(metadata.get("aliases", []))
        content: str = note["content"]

        candidates: list[str] = []

        # Title variations
        candidates += _title_variations(title)

        # Prominent noun phrases (capitalised multi-word sequences)
        for phrase in _extract_phrases(content):
            if phrase.lower() != title.lower():
                candidates.append(phrase)

        # Wikilink labels from other notes that point here
        stem = Path(path).stem
        for other_path in self._vault.list_files():
            if not other_path.endswith(".md") or other_path == path:
                continue
            other = self._vault.read_note(other_path)
            for link in other["metadata"].get("wikilinks", []):
                if "|" in link:
                    target, label = link.split("|", 1)
                    if target.strip() == stem:
                        candidates.append(label.strip())

        # Dedupe and filter
        seen = {a.lower() for a in existing}
        suggestions = []
        for c in candidates:
            if c.lower() not in seen and len(c) > 2:
                seen.add(c.lower())
                suggestions.append(c)
            if len(suggestions) >= limit:
                break

        return {
            "path": path,
            "existing_aliases": existing,
            "suggested_aliases": suggestions,
        }

    def add_aliases(self, path: str, aliases: list[str]) -> dict[str, Any]:
        """Merge new aliases into a note's frontmatter."""
        note = self._vault.read_note(path)
        content = note["content"]
        metadata = note["metadata"]
        existing: list[str] = list(metadata.get("aliases", []))

        new_aliases = [a for a in aliases if a not in existing]
        if not new_aliases:
            return {"path": path, "added": [], "aliases": existing}

        merged = existing + new_aliases
        # Rewrite aliases block in frontmatter
        alias_yaml = "aliases:\n" + "\n".join(f"  - {a}" for a in merged)

        if "aliases:" in content:
            content = re.sub(
                r"aliases:.*?(?=\n\w|\n---)",
                alias_yaml,
                content,
                flags=re.DOTALL,
            )
        else:
            # Insert after first ---
            end = content.find("\n---", 3)
            if end != -1:
                content = content[:end] + "\n" + alias_yaml + content[end:]

        self._vault.update_note(path, content)
        return {"path": path, "added": new_aliases, "aliases": merged}

    def suggest_keywords(self, path: str, limit: int = 8) -> dict[str, Any]:
        """Suggest high-value search keywords for a note.

        Keywords are terms that appear frequently in the note but are
        absent from the title, tags, and aliases — filling the gap
        between what the note *is called* and what it *talks about*.
        """
        note = self._vault.read_note(path)
        metadata = note["metadata"]
        content = note["content"]

        title = metadata.get("title") or Path(path).stem
        existing_terms = set(tokenize(title))
        for tag in metadata.get("tags", []):
            existing_terms.update(tokenize(tag))
        for alias in metadata.get("aliases", []):
            existing_terms.update(tokenize(alias))

        token_counts = Counter(tokenize(content))
        suggestions = [
            {"keyword": tok, "frequency": count}
            for tok, count in token_counts.most_common(limit * 3)
            if tok not in existing_terms and count >= _MIN_TOKEN_FREQ
        ][:limit]

        return {
            "path": path,
            "suggested_keywords": suggestions,
        }

    # ------------------------------------------------------------------ #
    # Vault-wide analysis
    # ------------------------------------------------------------------ #

    def find_poorly_indexed_notes(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return notes that are likely hard to find via search.

        A note is considered poorly indexed when it has:
        - No title in frontmatter
        - No aliases
        - No tags
        - A stem-only filename (no spaces, no description)
        """
        results: list[dict[str, Any]] = []
        for file_path in self._vault.list_files():
            if not file_path.endswith(".md"):
                continue
            note = self._vault.read_note(file_path)
            meta = note["metadata"]
            issues: list[str] = []

            if not meta.get("title"):
                issues.append("no title")
            if not meta.get("aliases"):
                issues.append("no aliases")
            if not meta.get("tags"):
                issues.append("no tags")
            if "_" in Path(file_path).stem or re.match(r"^[a-z0-9-]+$", Path(file_path).stem):
                issues.append("non-descriptive filename")

            if issues:
                results.append({
                    "path": file_path,
                    "issues": issues,
                    "score": len(issues),
                })

        return sorted(results, key=lambda r: (-r["score"], r["path"]))[:limit]

    def optimise_note(self, path: str) -> dict[str, Any]:
        """Run all optimisations on a single note and return a report.

        Does not write anything — returns suggestions only.
        """
        aliases = self.suggest_aliases(path)
        keywords = self.suggest_keywords(path)

        return {
            "path": path,
            "alias_suggestions": aliases["suggested_aliases"],
            "keyword_suggestions": keywords["suggested_keywords"],
            "tip": (
                "Add suggested aliases to frontmatter so Omnisearch and the "
                "quick-switcher can find this note by alternative names."
            ),
        }

    def bulk_optimise(self, folder: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        """Return optimisation reports for the most under-indexed notes."""
        poorly_indexed = self.find_poorly_indexed_notes(limit=limit * 2)
        if folder:
            prefix = folder.rstrip("/") + "/"
            poorly_indexed = [n for n in poorly_indexed if n["path"].startswith(prefix)]
        results = []
        for note_info in poorly_indexed[:limit]:
            results.append(self.optimise_note(note_info["path"]))
        return results


# ── Text-analysis helpers ──────────────────────────────────────────────

def _title_variations(title: str) -> list[str]:
    """Generate common alias forms for a title string."""
    variations: list[str] = []
    words = title.split()

    # Acronym from capital words
    acronym = "".join(w[0].upper() for w in words if w[0].isupper())
    if 2 <= len(acronym) < len(title):
        variations.append(acronym)

    # Lower-case version
    lower = title.lower()
    if lower != title:
        variations.append(lower)

    # Hyphenated slug
    slug = "-".join(w.lower() for w in words)
    if slug != title.lower():
        variations.append(slug)

    return variations


def _extract_phrases(content: str) -> list[str]:
    """Extract capitalised multi-word phrases as candidate aliases."""
    phrase_re = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)+)\b")
    counts: Counter[str] = Counter(m.group(0) for m in phrase_re.finditer(content))
    return [phrase for phrase, _ in counts.most_common(20)]
