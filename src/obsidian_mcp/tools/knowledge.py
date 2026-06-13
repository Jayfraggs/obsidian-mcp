"""Advanced knowledge-management MCP tool registration."""

from typing import Protocol

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.knowledge.service import KnowledgeService
from obsidian_mcp.vault.service import VaultService

KNOWLEDGE_TOOL_NAMES = (
    "build_moc",
    "create_atomic_note",
    "refactor_large_note",
    "suggest_backlinks",
    "auto_tag",
    "semantic_search",
    "detect_duplicates",
    "build_relationship_graph",
    "suggest_para_location",
    "suggest_johnny_decimal_location",
    "create_dataview_dashboard",
    "generate_excalidraw_architecture",
)


class ToolServer(Protocol):
    """Minimal MCP server protocol needed for tool registration."""

    def tool(self, name: str):  # type: ignore[no-untyped-def]
        """Return a decorator that registers an MCP tool."""


def register_knowledge_tools(
    server: ToolServer,
    settings: ObsidianMCPSettings,
    vault_service: VaultService | None = None,
) -> None:
    """Register advanced knowledge-management tools with an MCP server.

    Parameters
    ----------
    vault_service:
        Pre-built service (with adapter wired).  When *None* a default
        filesystem-backed service is created from ``settings.vault_path``.
    """
    service = vault_service or VaultService(settings.vault_path)
    knowledge_service = KnowledgeService(service)

    @server.tool("build_moc")
    def build_moc(topic: str, output_path: str | None = None, limit: int = 20):
        """Build a map-of-content note for a topic."""
        return knowledge_service.build_moc(topic, output_path, limit)

    @server.tool("create_atomic_note")
    def create_atomic_note(
        path: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        aliases: list[str] | None = None,
        source_links: list[str] | None = None,
    ):
        """Create a focused atomic note."""
        return knowledge_service.create_atomic_note(
            path, title, content, tags, aliases, source_links,
        )

    @server.tool("refactor_large_note")
    def refactor_large_note(path: str, create_notes: bool = False):
        """Return heading-based split proposals for a large note."""
        return knowledge_service.refactor_large_note(path, create_notes)

    @server.tool("suggest_backlinks")
    def suggest_backlinks(path: str, limit: int = 10):
        """Suggest candidate backlinks for a note."""
        return knowledge_service.suggest_backlinks(path, limit)

    @server.tool("auto_tag")
    def auto_tag(path: str, limit: int = 5):
        """Suggest tags for a note."""
        return knowledge_service.auto_tag(path, limit)

    @server.tool("semantic_search")
    def semantic_search(query: str, limit: int = 10):
        """Run deterministic local semantic-style search."""
        return knowledge_service.semantic_search(query, limit)

    @server.tool("detect_duplicates")
    def detect_duplicates(threshold: float = 82):
        """Detect likely duplicate notes."""
        return knowledge_service.detect_duplicates(threshold)

    @server.tool("build_relationship_graph")
    def build_relationship_graph():
        """Build a relationship graph across markdown notes."""
        return knowledge_service.build_relationship_graph()

    @server.tool("suggest_para_location")
    def suggest_para_location(path: str):
        """Suggest a PARA bucket for a note."""
        return knowledge_service.suggest_para_location(path)

    @server.tool("suggest_johnny_decimal_location")
    def suggest_johnny_decimal_location(path: str):
        """Return Johnny Decimal prefixes detected for a note path."""
        return knowledge_service.suggest_johnny_decimal_location(path)

    @server.tool("create_dataview_dashboard")
    def create_dataview_dashboard(
        path: str,
        title: str,
        tags: list[str] | None = None,
    ):
        """Create a Dataview-compatible dashboard note."""
        return knowledge_service.create_dataview_dashboard(path, title, tags)

    @server.tool("generate_excalidraw_architecture")
    def generate_excalidraw_architecture(path: str, title: str = "Architecture"):
        """Create an Excalidraw architecture note from the relationship graph."""
        return knowledge_service.generate_excalidraw_architecture(path, title)
