from obsidian_mcp.knowledge.analysis import (
    NoteDocument,
    build_dataview_dashboard,
    build_relationship_graph,
    classify_para,
    detect_duplicate_notes,
    generate_excalidraw_markdown,
    parse_johnny_decimal_prefix,
    semantic_rank,
    suggest_tags,
    tokenize,
)


def test_tokenize_normalizes_words_and_removes_short_noise() -> None:
    assert tokenize("Project: AI Knowledge, maps!") == ["project", "knowledge", "maps"]


def test_semantic_rank_combines_token_overlap_and_fuzzy_score() -> None:
    docs = [
        NoteDocument(path="One.md", title="Project Alpha", content="planning knowledge graph"),
        NoteDocument(path="Two.md", title="Garden", content="plants and water"),
    ]

    results = semantic_rank("knowledge project", docs)

    assert results[0]["path"] == "One.md"
    assert results[0]["score"] > results[1]["score"]


def test_detect_duplicate_notes_finds_similar_titles_and_content() -> None:
    docs = [
        NoteDocument(path="A.md", title="Atomic Notes", content="Small focused evergreen notes"),
        NoteDocument(path="B.md", title="Atomic Note", content="Small focused evergreen note"),
        NoteDocument(path="C.md", title="Cooking", content="Recipe collection"),
    ]

    duplicates = detect_duplicate_notes(docs, threshold=70)

    assert duplicates == [{"first": "A.md", "second": "B.md", "score": duplicates[0]["score"]}]
    assert duplicates[0]["score"] >= 70


def test_classify_para_uses_path_tags_and_content_terms() -> None:
    doc = NoteDocument(path="Notes/Launch.md", title="Launch", content="deadline project milestone")

    assert classify_para(doc) == "Projects"
    assert classify_para(NoteDocument(path="Areas/Health.md", title="Health", content="habit")) == "Areas"


def test_parse_johnny_decimal_prefix_reads_area_and_item() -> None:
    assert parse_johnny_decimal_prefix("10-19 Knowledge/11 Notes/11.01 Atomic") == {
        "area": "10-19",
        "category": "11",
        "item": "11.01",
    }


def test_suggest_tags_prefers_existing_tags_and_content_terms() -> None:
    doc = NoteDocument(path="Graph.md", title="Graph", content="Knowledge graph graph links")

    suggestions = suggest_tags(doc, existing_tags=["knowledge", "project"], limit=2)

    assert suggestions[0]["tag"] == "knowledge"
    assert len(suggestions) == 2


def test_build_relationship_graph_uses_links_and_tags() -> None:
    docs = [
        NoteDocument(path="A.md", title="A", content="See [[B]]", tags=["x"], links=["B"]),
        NoteDocument(path="B.md", title="B", content="Back", tags=["x"]),
    ]

    graph = build_relationship_graph(docs)

    assert graph["nodes"] == [
        {"id": "A.md", "title": "A", "tags": ["x"]},
        {"id": "B.md", "title": "B", "tags": ["x"]},
    ]
    assert {"source": "A.md", "target": "B.md", "type": "link"} in graph["edges"]
    assert {"source": "A.md", "target": "B.md", "type": "tag", "tag": "x"} in graph["edges"]


def test_build_dataview_dashboard_contains_expected_query_blocks() -> None:
    markdown = build_dataview_dashboard("Knowledge", tags=["project", "knowledge"])

    assert "# Knowledge Dashboard" in markdown
    assert "TABLE file.mtime AS Updated" in markdown
    assert 'contains(file.tags, "#project")' in markdown


def test_generate_excalidraw_markdown_contains_diagram_json() -> None:
    graph = {
        "nodes": [{"id": "A.md", "title": "A", "tags": []}, {"id": "B.md", "title": "B", "tags": []}],
        "edges": [{"source": "A.md", "target": "B.md", "type": "link"}],
    }

    markdown = generate_excalidraw_markdown("Architecture", graph)

    assert "excalidraw-plugin: parsed" in markdown
    assert '"type": "rectangle"' in markdown
    assert '"type": "arrow"' in markdown
