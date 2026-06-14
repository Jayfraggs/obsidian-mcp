"""Configuration models and loading for the Obsidian MCP server."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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


class ObsidianMCPSettings(BaseSettings):
    """Validated runtime settings. All keys use prefix OBSIDIAN_MCP_."""

    model_config = SettingsConfigDict(
        env_prefix="OBSIDIAN_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Core ─────────────────────────────────────────────────────────
    vault_path: Path = Field(
        description="Absolute path to the Obsidian vault directory."
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

    @field_validator("vault_path")
    @classmethod
    def vault_path_must_exist(cls, value: Path) -> Path:
        if not value.exists():
            raise ValueError(
                f"Vault path does not exist: {value}\n"
                f"Set OBSIDIAN_MCP_VAULT_PATH to an existing directory."
            )
        if not value.is_dir():
            raise ValueError(f"Vault path must be a directory, not a file: {value}")
        return value.resolve()


def load_settings() -> ObsidianMCPSettings:
    """Load and validate settings from environment / .env file."""
    return ObsidianMCPSettings()
