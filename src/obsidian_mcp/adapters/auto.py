"""Auto adapter – selects the best available backend at startup.

Priority (when MODE=auto):
  1. RestApiAdapter   – if OBSIDIAN_MCP_ADAPTER_API_KEY is set and plugin responds
  2. FilesystemAdapter – always available as a safe fallback

Modes (OBSIDIAN_MCP_ADAPTER_MODE):
  auto        probe REST first, fall back silently (default)
  rest        REST only – raise ConfigurationError if unreachable
  filesystem  filesystem only – skip probe entirely
"""

from __future__ import annotations

import logging

from obsidian_mcp.errors import ConfigurationError
from .base import ObsidianAdapter, RawNote, RawSearchResult
from .filesystem import FilesystemAdapter
from .rest_api import RestApiAdapter

logger = logging.getLogger("obsidian_mcp.adapters.auto")


class AutoAdapter(ObsidianAdapter):
    """Transparent delegating adapter.  Chosen backend is fixed at construction."""

    def __init__(self, backend: ObsidianAdapter) -> None:
        self._backend = backend
        logger.info(
            "AutoAdapter delegating to %s", type(backend).__name__
        )

    @classmethod
    def from_settings(cls, settings: "ObsidianMCPSettings") -> "AutoAdapter":  # type: ignore[name-defined]
        """Factory: read adapter settings and return a ready AutoAdapter.

        Import inside the method to avoid a circular import at module load.
        """
        from obsidian_mcp.config import AdapterMode  # local import

        mode = settings.adapter_mode
        vault_path = settings.vault_path

        # ── REST-only mode ──────────────────────────────────────────────
        if mode is AdapterMode.REST:
            if not settings.adapter_api_key:
                raise ConfigurationError(
                    "adapter_mode=rest requires OBSIDIAN_MCP_ADAPTER_API_KEY to be set."
                )
            adapter = RestApiAdapter(
                api_key=settings.adapter_api_key,
                host=settings.adapter_host,
                port=settings.adapter_port,
            )
            if not adapter.health_check():
                raise ConfigurationError(
                    f"adapter_mode=rest but REST API is unreachable at "
                    f"{settings.adapter_host}:{settings.adapter_port}."
                )
            return cls(adapter)

        # ── Filesystem-only mode ────────────────────────────────────────
        if mode is AdapterMode.FILESYSTEM:
            return cls(FilesystemAdapter(vault_path))

        # ── Auto mode (default) ─────────────────────────────────────────
        if settings.adapter_api_key:
            rest = RestApiAdapter(
                api_key=settings.adapter_api_key,
                host=settings.adapter_host,
                port=settings.adapter_port,
            )
            if rest.health_check():
                logger.info(
                    "REST API reachable at %s:%s – using RestApiAdapter.",
                    settings.adapter_host,
                    settings.adapter_port,
                )
                return cls(rest)
            logger.warning(
                "OBSIDIAN_MCP_ADAPTER_API_KEY is set but REST API is unreachable – "
                "falling back to FilesystemAdapter."
            )
        else:
            logger.info(
                "No OBSIDIAN_MCP_ADAPTER_API_KEY configured – using FilesystemAdapter."
            )

        return cls(FilesystemAdapter(vault_path))

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__

    # ------------------------------------------------------------------ #
    # Delegate all operations to the chosen backend
    # ------------------------------------------------------------------ #

    def read_note(self, path: str) -> RawNote:
        return self._backend.read_note(path)

    def write_note(self, path: str, content: str) -> None:
        self._backend.write_note(path, content)

    def append_note(self, path: str, content: str) -> None:
        self._backend.append_note(path, content)

    def delete_note(self, path: str) -> None:
        self._backend.delete_note(path)

    def move_note(self, source: str, destination: str) -> None:
        self._backend.move_note(source, destination)

    def list_files(self) -> list[str]:
        return self._backend.list_files()

    def list_folders(self) -> list[str]:
        return self._backend.list_folders()

    def search_notes(self, query: str, limit: int = 10) -> list[RawSearchResult]:
        return self._backend.search_notes(query, limit)

    def health_check(self) -> bool:
        return self._backend.health_check()
