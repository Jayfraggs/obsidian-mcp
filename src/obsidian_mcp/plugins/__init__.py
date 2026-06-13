"""Obsidian MCP – plugin-aware services layer.

Each service generates or inspects Obsidian plugin-compatible markdown
content using only ``VaultService`` as a dependency.

Usage::

    from obsidian_mcp.plugins import (
        DataviewService,
        TasksService,
        TemplaterService,
        ExcalidrawService,
        OmnisearchService,
    )
    dv  = DataviewService(vault_service)
    ts  = TasksService(vault_service)
    tpl = TemplaterService(vault_service)
    ex  = ExcalidrawService(vault_service)
    om  = OmnisearchService(vault_service)
"""

from .dataview import DataviewService
from .excalidraw import ExcalidrawService
from .omnisearch import OmnisearchService
from .tasks import TasksService
from .templater import TemplaterService

__all__ = [
    "DataviewService",
    "ExcalidrawService",
    "OmnisearchService",
    "TasksService",
    "TemplaterService",
]
