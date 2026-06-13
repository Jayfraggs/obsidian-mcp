"""Obsidian MCP – adapter layer.

Public surface::

    from obsidian_mcp.adapters import AutoAdapter, ObsidianAdapter
    adapter = AutoAdapter.from_settings(settings)
"""

from .base import ObsidianAdapter, RawNote, RawSearchResult
from .filesystem import FilesystemAdapter
from .rest_api import RestApiAdapter
from .auto import AutoAdapter

__all__ = [
    "ObsidianAdapter",
    "RawNote",
    "RawSearchResult",
    "FilesystemAdapter",
    "RestApiAdapter",
    "AutoAdapter",
]
