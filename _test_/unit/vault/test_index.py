from pathlib import Path

from obsidian_mcp.vault.index import BacklinkIndex


def test_build_indexes_wikilink_backlinks(tmp_path: Path) -> None:
    (tmp_path / "Target.md").write_text("# Target\n", encoding="utf-8")
    (tmp_path / "Source.md").write_text("[[Target]]\n", encoding="utf-8")

    index = BacklinkIndex(tmp_path)
    index._cache_path = tmp_path / "index-cache.json"

    index.build()

    assert index.find("Target.md") == ["Source.md"]
