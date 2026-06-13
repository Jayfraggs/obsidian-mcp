from collections.abc import Callable
from pathlib import Path
from typing import Any

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.tools.knowledge import KNOWLEDGE_TOOL_NAMES, register_knowledge_tools


class FakeMCPServer:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name] = func
            return func

        return decorator


def test_register_knowledge_tools_adds_expected_tools(tmp_path: Path) -> None:
    server = FakeMCPServer()
    settings = ObsidianMCPSettings(vault_path=tmp_path)

    register_knowledge_tools(server, settings)

    assert sorted(server.tools) == sorted(KNOWLEDGE_TOOL_NAMES)


def test_registered_atomic_note_handler_uses_knowledge_service(tmp_path: Path) -> None:
    server = FakeMCPServer()
    settings = ObsidianMCPSettings(vault_path=tmp_path)
    register_knowledge_tools(server, settings)

    result = server.tools["create_atomic_note"](
        "Atoms/Idea",
        "Idea",
        "Focused",
        ["idea"],
        ["Alias"],
        ["Source"],
    )

    assert result["path"] == "Atoms/Idea.md"
