from obsidian_mcp.vault.metadata import extract_note_metadata


def test_extract_note_metadata_reads_frontmatter_aliases_and_tags() -> None:
    content = """---
title: Project Home
aliases:
  - Home
tags:
  - project
  - status/active
---
# Body
Inline #meeting tag.
"""

    metadata = extract_note_metadata("Project.md", content)

    assert metadata.title == "Project Home"
    assert metadata.aliases == ["Home"]
    assert metadata.tags == ["meeting", "project", "status/active"]


def test_extract_note_metadata_finds_links_tasks_and_dataview_fields() -> None:
    content = """# Note
related:: [[Other Note]]
owner:: Jane
- [ ] Review task
- [x] Done task
See [[Target|label]] and [Markdown Link](Folder/Linked.md).
"""

    metadata = extract_note_metadata("Note.md", content)

    assert metadata.wikilinks == ["Other Note", "Target"]
    assert metadata.markdown_links == ["Folder/Linked.md"]
    assert metadata.task_count == 2
    assert metadata.dataview_fields == {"owner": "Jane", "related": "[[Other Note]]"}


def test_extract_note_metadata_detects_templater_and_excalidraw() -> None:
    content = """---
excalidraw-plugin: parsed
---
<% tp.file.title %>
"""

    metadata = extract_note_metadata("Sketch.excalidraw.md", content)

    assert metadata.has_templater is True
    assert metadata.is_excalidraw is True
