from collections.abc import Callable
from pathlib import Path
from typing import Any

from obsidian_mcp.config import ObsidianMCPSettings
from obsidian_mcp.tools.core import CORE_TOOL_NAMES, register_core_tools


class FakeMCPServer:
    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def tool(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[name] = func
            return func

        return decorator


def test_register_core_tools_adds_all_expected_tools(tmp_path: Path) -> None:
    server = FakeMCPServer()
    settings = ObsidianMCPSettings(vault_path=tmp_path)

    register_core_tools(server, settings)

    assert sorted(server.tools) == sorted(CORE_TOOL_NAMES)


def test_registered_create_and_read_note_handlers_use_vault_service(tmp_path: Path) -> None:
    server = FakeMCPServer()
    settings = ObsidianMCPSettings(vault_path=tmp_path)
    register_core_tools(server, settings)

    created = server.tools["create_note"]("Note", "content")
    read = server.tools["read_note"]("Note")

    assert created["path"] == "Note.md"
    assert read["content"] == "content"
