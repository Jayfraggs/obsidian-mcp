"""Configuration models and loading for the Obsidian MCP server."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from obsidian_mcp.permissions import PermissionProfile


class LogLevel(StrEnum):
    DEBUG    = "DEBUG"
    INFO     = "INFO"
    WARNING  = "WARNING"
    ERROR    = "ERROR"
    CRITICAL = "CRITICAL"


class AdapterMode(StrEnum):
    """Vault adapter selection strategy.

    auto        – probe REST API first, fall back to filesystem (default)
    rest        – REST API only; raise on startup if unreachable
    filesystem  – direct pathlib access only
    """
    AUTO       = "auto"
    REST       = "rest"
    FILESYSTEM = "filesystem"


_VAULT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,47}$")


class VaultConfig(BaseModel):
    """One configured vault.

    Adapter settings are **not** inherited from the global settings (except for
    the legacy ``vault_path`` vault): sharing one Local REST API key/port between
    vaults would silently route reads and writes to the wrong vault.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Short handle used to address the vault, e.g. 'work'.")
    path: Path = Field(description="Absolute path to the vault folder.")
    description: str = Field(default="", description="Shown to the AI to help it pick the right vault.")
    adapter_mode: AdapterMode = AdapterMode.AUTO
    adapter_api_key: str = ""
    adapter_host: str = "127.0.0.1"
    adapter_port: int = Field(default=27123, ge=1, le=65535)

    @field_validator("name")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        value = value.strip()
        if not _VAULT_NAME_RE.match(value):
            raise ValueError(
                f"Invalid vault name {value!r}: use 1-48 letters, digits, '-', '_' or '.' "
                "(no spaces), starting with a letter or digit."
            )
        return value

    @field_validator("path")
    @classmethod
    def _path_must_exist(cls, value: Path) -> Path:
        value = value.expanduser()
        if not value.exists():
            raise ValueError(f"Vault path does not exist: {value}")
        if not value.is_dir():
            raise ValueError(f"Vault path must be a directory, not a file: {value}")
        return value.resolve()

    @property
    def vault_path(self) -> Path:
        """Alias so a VaultConfig can be handed to ``AutoAdapter.from_settings``."""
        return self.path

    @property
    def uses_rest(self) -> bool:
        return self.adapter_mode is not AdapterMode.FILESYSTEM and bool(self.adapter_api_key)


def validate_vault_entries(entries: list[VaultConfig]) -> None:
    """Raise ``ValueError`` if names, folders or REST endpoints collide across *entries*."""
    seen_names: dict[str, str] = {}
    seen_paths: dict[Path, str] = {}
    seen_rest: dict[tuple[str, int], str] = {}
    for e in entries:
        if e.name.lower() in seen_names:
            raise ValueError(f"Duplicate vault name {e.name!r} (names are case-insensitive).")
        if e.path in seen_paths:
            raise ValueError(f"Vaults {seen_paths[e.path]!r} and {e.name!r} point to the same folder: {e.path}")
        if e.uses_rest:
            endpoint = (e.adapter_host, e.adapter_port)
            if endpoint in seen_rest:
                raise ValueError(
                    f"Vaults {seen_rest[endpoint]!r} and {e.name!r} both use the REST endpoint "
                    f"{endpoint[0]}:{endpoint[1]}; each vault needs its own Local REST API port "
                    "(or leave adapter_api_key empty to use direct file access)."
                )
            seen_rest[endpoint] = e.name
        seen_names[e.name.lower()] = e.name
        seen_paths[e.path] = e.name


def parse_vaults_spec(text: str) -> list[dict[str, Any]]:
    """Parse ``OBSIDIAN_MCP_VAULTS``.

    Accepts either the shorthand ``work=C:\\Vaults\\Work;personal=D:\\Notes``
    (filesystem access, entries separated by ``;`` or newlines) or a JSON list of
    vault objects for full control (descriptions, per-vault REST settings).
    """
    s = text.strip()
    if not s:
        return []
    if s[0] in "[{":
        try:
            data = json.loads(s)
        except json.JSONDecodeError as exc:
            raise ValueError(f"OBSIDIAN_MCP_VAULTS looks like JSON but does not parse: {exc}") from exc
        if isinstance(data, dict):
            data = data["vaults"] if isinstance(data.get("vaults"), list) else [data]
        if not isinstance(data, list):
            raise ValueError("OBSIDIAN_MCP_VAULTS JSON must be a list of vault objects")
        return data
    items: list[dict[str, Any]] = []
    for chunk in re.split(r"[;\n]+", s):
        chunk = chunk.strip()
        if not chunk:
            continue
        name, sep, path = chunk.partition("=")
        if not sep or not name.strip() or not path.strip():
            raise ValueError(
                f"Invalid vault entry {chunk!r}: expected name=path "
                "(separate several vaults with ';')."
            )
        items.append({"name": name.strip(), "path": path.strip().strip("\"'")})
    return items


class ObsidianMCPSettings(BaseSettings):
    """Validated runtime settings. All keys use prefix OBSIDIAN_MCP_."""

    model_config = SettingsConfigDict(
        env_prefix="OBSIDIAN_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Core ─────────────────────────────────────────────────────────
    vault_path: Path | None = Field(
        default=None,
        description=(
            "Absolute path to the Obsidian vault directory (single-vault setup). "
            "With several vaults it is kept as the primary vault's path."
        ),
    )
    vaults: Annotated[list[VaultConfig], NoDecode] = Field(
        default_factory=list,
        description=(
            "Multiple vaults: OBSIDIAN_MCP_VAULTS='work=/path/a;personal=/path/b' "
            "or a JSON list of {name, path, description?, adapter_*?}."
        ),
    )
    default_vault: str = Field(
        default="",
        description="Name of the vault that is active at startup (default: the first one).",
    )
    server_name: str = Field(default="obsidian-mcp", min_length=1)
    log_level: LogLevel = LogLevel.INFO
    permission_profile: PermissionProfile = PermissionProfile.SAFE_WRITE

    # ── Web UI ────────────────────────────────────────────────────────
    web_host: str = "127.0.0.1"
    web_port: int = Field(default=8765, ge=1, le=65535)

    # ── Adapter ──────────────────────────────────────────────────────
    adapter_mode: AdapterMode = AdapterMode.AUTO
    adapter_api_key: str = Field(
        default="",
        description="Obsidian Local REST API plugin key (OBSIDIAN_MCP_ADAPTER_API_KEY).",
    )
    adapter_host: str = Field(default="127.0.0.1")
    adapter_port: int = Field(default=27123, ge=1, le=65535)

    # ── Templater ────────────────────────────────────────────────────
    templates_folder: str = Field(
        default="Templates",
        description="Vault-relative folder where Templater templates live.",
    )

    @field_validator("vaults", mode="before")
    @classmethod
    def _parse_vaults(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return parse_vaults_spec(value)
        return value

    @field_validator("vault_path")
    @classmethod
    def vault_path_must_exist(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        if not value.exists():
            raise ValueError(
                f"Vault path does not exist: {value}\n"
                f"Set OBSIDIAN_MCP_VAULT_PATH to an existing directory."
            )
        if not value.is_dir():
            raise ValueError(f"Vault path must be a directory, not a file: {value}")
        return value.resolve()

    @model_validator(mode="after")
    def _resolve_vaults(self) -> "ObsidianMCPSettings":
        """Fold ``vault_path`` and ``vaults`` into one validated list; pick the primary."""
        entries = list(self.vaults)
        if self.vault_path is not None and all(e.path != self.vault_path for e in entries):
            taken = {e.name.lower() for e in entries}
            name = "default" if "default" not in taken else "primary"
            # The legacy vault keeps using the global adapter settings (backward compatible).
            entries.insert(0, VaultConfig(
                name=name, path=self.vault_path, adapter_mode=self.adapter_mode,
                adapter_api_key=self.adapter_api_key, adapter_host=self.adapter_host,
                adapter_port=self.adapter_port,
            ))
        if not entries:
            raise ValueError(
                "No vault configured. Set OBSIDIAN_MCP_VAULT_PATH (one vault) or "
                "OBSIDIAN_MCP_VAULTS='name=path;name=path' (several vaults)."
            )
        validate_vault_entries(entries)
        wanted = self.default_vault.strip()
        primary = entries[0]
        if wanted:
            match = next((e for e in entries if e.name.lower() == wanted.lower()), None)
            if match is None:
                raise ValueError(
                    f"default_vault {wanted!r} is not one of the configured vaults: "
                    f"{', '.join(e.name for e in entries)}."
                )
            primary = match
        self.vaults = entries
        self.default_vault = primary.name
        self.vault_path = primary.path
        return self


def load_settings() -> ObsidianMCPSettings:
    """Load and validate settings from environment / .env file."""
    return ObsidianMCPSettings()
