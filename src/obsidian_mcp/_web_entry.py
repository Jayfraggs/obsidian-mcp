"""Standalone entry point for the Web UI.

Kept in a separate module so the obsidian-mcp-web.exe script file
is distinct from obsidian-mcp.exe — preventing Windows file-locking
conflicts when both are installed in the same venv.

obsidian-mcp-web = "obsidian_mcp._web_entry:main"
"""

from obsidian_mcp.__main__ import web_main as main  # noqa: F401
