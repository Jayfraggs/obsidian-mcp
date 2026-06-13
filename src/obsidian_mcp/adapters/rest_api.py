"""REST API adapter – communicates with the Obsidian Local REST API plugin.

Plugin: https://github.com/coddingtonbear/obsidian-local-rest-api

Required settings (via ObsidianMCPSettings):
    OBSIDIAN_MCP_ADAPTER_API_KEY   – from the plugin settings page
    OBSIDIAN_MCP_ADAPTER_HOST      – default 127.0.0.1
    OBSIDIAN_MCP_ADAPTER_PORT      – default 27123
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

import httpx

from obsidian_mcp.errors import NoteNotFoundError, NoteAlreadyExistsError, VaultOperationError
from .base import ObsidianAdapter, RawNote, RawSearchResult

logger = logging.getLogger("obsidian_mcp.adapters.rest_api")

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 27123


class RestApiAdapter(ObsidianAdapter):
    """Adapter that proxies all vault I/O through the Obsidian REST API plugin."""

    def __init__(
        self,
        api_key: str,
        host: str = _DEFAULT_HOST,
        port: int = _DEFAULT_PORT,
    ) -> None:
        self._base = f"https://{host}:{port}"
        # The plugin uses a self-signed cert; disable verification for localhost use.
        self._client = httpx.Client(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "text/markdown",
            },
            verify=False,
            timeout=10.0,
        )
        logger.info("RestApiAdapter active → %s", self._base)

    # ------------------------------------------------------------------ #
    # Note CRUD
    # ------------------------------------------------------------------ #

    def read_note(self, path: str) -> RawNote:
        resp = self._client.get(f"{self._base}/vault/{self._enc(path)}")
        if resp.status_code == 404:
            return RawNote(path=path, content="", exists=False)
        self._raise_for_status(resp, path)
        return RawNote(path=path, content=resp.text)

    def write_note(self, path: str, content: str) -> None:
        resp = self._client.put(
            f"{self._base}/vault/{self._enc(path)}",
            content=content.encode(),
        )
        self._raise_for_status(resp, path)

    def append_note(self, path: str, content: str) -> None:
        # REST API PATCH appends to the note
        resp = self._client.request(
            "PATCH",
            f"{self._base}/vault/{self._enc(path)}",
            content=content.encode(),
            headers={"Content-Insertion-Position": "end"},
        )
        if resp.status_code == 404:
            raise NoteNotFoundError("Note was not found.")
        self._raise_for_status(resp, path)

    def delete_note(self, path: str) -> None:
        resp = self._client.delete(f"{self._base}/vault/{self._enc(path)}")
        if resp.status_code == 404:
            raise NoteNotFoundError("Note was not found.")
        self._raise_for_status(resp, path)

    def move_note(self, source: str, destination: str) -> None:
        # REST API has no dedicated move endpoint – read → write → delete.
        note = self.read_note(source)
        if not note.exists:
            raise NoteNotFoundError("Note was not found.")
        dest_check = self.read_note(destination)
        if dest_check.exists:
            raise NoteAlreadyExistsError("Destination note already exists.")
        self.write_note(destination, note.content)
        self.delete_note(source)
        logger.debug("Moved note via REST: %s → %s", source, destination)

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #

    def list_files(self) -> list[str]:
        resp = self._client.get(f"{self._base}/vault/")
        if resp.status_code != 200:
            return []
        data = resp.json()
        return sorted(data.get("files", []))

    def list_folders(self) -> list[str]:
        resp = self._client.get(f"{self._base}/vault/")
        if resp.status_code != 200:
            return []
        data = resp.json()
        return sorted(data.get("folders", []))

    def search_notes(self, query: str, limit: int = 10) -> list[RawSearchResult]:
        resp = self._client.post(
            f"{self._base}/search/simple/",
            params={"query": query, "contextLength": 120},
        )
        if resp.status_code != 200:
            return []
        results: list[RawSearchResult] = []
        for item in resp.json()[:limit]:
            results.append(RawSearchResult(
                path=item.get("filename", ""),
                score=round(float(item.get("score", 0)), 2),
                preview=item.get("context", ""),
            ))
        return results

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #

    def health_check(self) -> bool:
        try:
            resp = self._client.get(f"{self._base}/")
            return resp.status_code == 200
        except Exception:
            return False

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _enc(path: str) -> str:
        return quote(path, safe="/")

    @staticmethod
    def _raise_for_status(resp: httpx.Response, path: str) -> None:
        if resp.is_success:
            return
        raise VaultOperationError(
            f"REST API error {resp.status_code} for path '{path}'.",
            internal_detail=resp.text[:200],
        )
