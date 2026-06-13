from pathlib import Path

from obsidian_mcp.knowledge.service import KnowledgeService
from obsidian_mcp.vault.service import VaultService


def test_build_moc_creates_topic_map_note(tmp_path: Path) -> None:
    vault = VaultService(tmp_path)
    vault.create_note("Project Alpha", "# Alpha\nKnowledge graph planning #project")
    vault.create_note("Garden", "# Garden\nPlants")
    service = KnowledgeService(vault)

    result = service.build_moc("Knowledge", output_path="MOCs/Knowledge")

    assert result["path"] == "MOCs/Knowledge.md"
    assert "[[Project Alpha]]" in vault.read_note("MOCs/Knowledge")["content"]


def test_create_atomic_note_writes_frontmatter_and_source_links(tmp_path: Path) -> None:
    service = KnowledgeService(VaultService(tmp_path))

    result = service.create_atomic_note(
        path="Atoms/Idea",
        title="One Idea",
        content="Focused content",
        tags=["idea"],
        aliases=["Concept"],
        source_links=["Source"],
    )

    content = service.vault.read_note("Atoms/Idea")["content"]
    assert result["path"] == "Atoms/Idea.md"
    assert "aliases:" in content
    assert "[[Source]]" in content


def test_refactor_large_note_returns_heading_based_proposals(tmp_path: Path) -> None:
    vault = VaultService(tmp_path)
    vault.create_note("Long", "# Long\n## First Idea\nA\n## Second Idea\nB")
    service = KnowledgeService(vault)

    result = service.refactor_large_note("Long")

    assert result["source"] == "Long.md"
    assert [item["title"] for item in result["proposals"]] == ["First Idea", "Second Idea"]


def test_suggest_backlinks_and_auto_tag(tmp_path: Path) -> None:
    vault = VaultService(tmp_path)
    vault.create_note("Target", "# Target\nKnowledge graph planning")
    vault.create_note("Related", "# Related\nKnowledge graph links #knowledge")
    service = KnowledgeService(vault)

    backlinks = service.suggest_backlinks("Target", limit=1)
    tags = service.auto_tag("Target", limit=2)

    assert backlinks[0]["path"] == "Related.md"
    assert tags[0]["tag"] == "knowledge"


def test_semantic_search_duplicates_and_relationship_graph(tmp_path: Path) -> None:
    vault = VaultService(tmp_path)
    vault.create_note("A", "# Atomic Notes\nSmall focused evergreen notes [[B]] #x")
    vault.create_note("B", "# Atomic Note\nSmall focused evergreen note #x")
    service = KnowledgeService(vault)

    search = service.semantic_search("focused note")
    duplicates = service.detect_duplicates(threshold=70)
    graph = service.build_relationship_graph()

    assert search[0]["path"] in {"A.md", "B.md"}
    assert duplicates[0]["first"] == "A.md"
    assert {"source": "A.md", "target": "B.md", "type": "link"} in graph["edges"]


def test_para_johnny_dashboard_and_excalidraw_generation(tmp_path: Path) -> None:
    vault = VaultService(tmp_path)
    vault.create_note("10-19 Knowledge/11 Notes/11.01 Atomic", "# Atomic\nproject milestone #project")
    service = KnowledgeService(vault)

    para = service.suggest_para_location("10-19 Knowledge/11 Notes/11.01 Atomic")
    johnny = service.suggest_johnny_decimal_location("10-19 Knowledge/11 Notes/11.01 Atomic")
    dashboard = service.create_dataview_dashboard("Dashboards/Knowledge", title="Knowledge")
    drawing = service.generate_excalidraw_architecture("Diagrams/Architecture")

    assert para["bucket"] == "Projects"
    assert johnny["area"] == "10-19"
    assert dashboard["path"] == "Dashboards/Knowledge.md"
    assert drawing["path"] == "Diagrams/Architecture.excalidraw.md"
