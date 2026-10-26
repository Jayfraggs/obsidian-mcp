"""Multi-vault support: a registry of configured vaults plus a routing proxy.

Model
-----
* ``VaultRegistry`` knows every configured vault and builds each
  :class:`VaultService` **lazily** (adapter probe + backlink index + file
  watcher), so a vault whose Obsidian instance is offline cannot stop the
  server from starting.  Only the default vault is built at launch.
* Exactly one vault is *active* at a time (``vault_switch``).  A single tool call
  can target another vault without switching — ``registry.use(name)`` sets a
  context-local override that is restored afterwards.
* ``VaultRouter`` is duck-typed as a ``VaultService``: every attribute access is
  forwarded to the registry's *current* vault.  All existing services
  (Dataview, Kanban, Knowledge, …) only hold a reference to "the vault", so
  handing them a router makes the whole tool suite multi-vault with no change
  to any tool body.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator, Sequence
from contextvars import ContextVar
from typing import Any

from obsidian_mcp.config import AdapterMode, VaultConfig, validate_vault_entries
from obsidian_mcp.errors import ConfigurationError, UnknownVaultError
from obsidian_mcp.logging import get_logger
from obsidian_mcp.vault.service import VaultService

logger = get_logger("registry")

VaultFactory = Callable[[VaultConfig], VaultService]


def build_vault_service(cfg: VaultConfig) -> VaultService:
    """Default factory: pick the adapter from the vault's *own* settings."""
    from obsidian_mcp.adapters import AutoAdapter  # local import: avoids a cycle at import time

    adapter = AutoAdapter.from_settings(cfg)   # VaultConfig exposes the attributes it reads
    logger.info("Vault %r: adapter %s", cfg.name, adapter.backend_name)
    return VaultService(cfg.path, adapter=adapter)


class VaultRegistry:
    """Holds the configured vaults and tracks which one is active."""

    def __init__(
        self,
        configs: Sequence[VaultConfig],
        *,
        default: str | None = None,
        factory: VaultFactory | None = None,
    ) -> None:
        if not configs:
            raise ConfigurationError("VaultRegistry needs at least one vault.")
        self._order = [c.name for c in configs]
        self._configs = {c.name.lower(): c for c in configs}
        self._factory: VaultFactory = factory or build_vault_service
        self._services: dict[str, VaultService] = {}
        self._lock = threading.RLock()
        self._override: ContextVar[str | None] = ContextVar(f"obsidian_mcp_vault_{id(self)}", default=None)
        self._default = self.config(default).name if default else self._order[0]
        self._active = self._default

    # ------------------------------------------------------------------ #
    # Lookup
    # ------------------------------------------------------------------ #

    def __len__(self) -> int:
        return len(self._order)

    def names(self) -> list[str]:
        return list(self._order)

    @property
    def default_name(self) -> str:
        return self._default

    def config(self, name: str | None) -> VaultConfig:
        """Case-insensitive lookup; raises :class:`UnknownVaultError` with the valid names."""
        key = (name or "").strip().lower()
        try:
            return self._configs[key]
        except KeyError:
            raise UnknownVaultError(name or "", self._order) from None

    # ------------------------------------------------------------------ #
    # Active / per-call selection
    # ------------------------------------------------------------------ #

    @property
    def active_name(self) -> str:
        return self._active

    def set_active(self, name: str) -> VaultConfig:
        cfg = self.config(name)
        with self._lock:
            self._active = cfg.name
        logger.info("Active vault is now %r", cfg.name)
        return cfg

    def current_name(self) -> str:
        """The vault a call made *right now* would hit (per-call override, else active)."""
        return self._override.get() or self._active

    @contextlib.contextmanager
    def use(self, name: str | None) -> Iterator[VaultConfig]:
        """Run the enclosed calls against *name* without changing the active vault."""
        cfg = self.config(name) if name else self.config(self.current_name())
        token = self._override.set(cfg.name)
        try:
            yield cfg
        finally:
            self._override.reset(token)

    # ------------------------------------------------------------------ #
    # Services
    # ------------------------------------------------------------------ #

    def get(self, name: str | None = None) -> VaultService:
        """Return (building and starting on first use) the service for *name* / the current vault."""
        cfg = self.config(name or self.current_name())
        with self._lock:
            svc = self._services.get(cfg.name)
            if svc is None:
                logger.info("Starting vault %r (%s)", cfg.name, cfg.path)
                svc = self._factory(cfg)
                svc.start()
                self._services[cfg.name] = svc
            return svc

    def current(self) -> VaultService:
        return self.get(None)

    def configs(self) -> list[VaultConfig]:
        return [self._configs[n.lower()] for n in self._order]

    def reset(self, name: str) -> None:
        """Stop and forget a vault's service; it is rebuilt (with current settings) on next use."""
        cfg = self.config(name)
        with self._lock:
            svc = self._services.pop(cfg.name, None)
        if svc is not None:
            try:
                svc.stop()
            except Exception:  # pragma: no cover - best effort
                logger.exception("Error stopping vault %r", cfg.name)

    def update_adapter(
        self,
        name: str,
        *,
        api_key: str | None = None,
        host: str | None = None,
        port: int | None = None,
        mode: AdapterMode | None = None,
    ) -> VaultConfig:
        """Change one vault's REST settings.  ``None`` keeps the current value.

        The whole vault set is re-validated first (``ValueError`` if two vaults would
        share a REST endpoint) and nothing changes on failure.  The vault's service
        is reset so the new key takes effect on next use.
        """
        with self._lock:
            old = self.config(name)
            changes = {k: v for k, v in (
                ("adapter_api_key", api_key), ("adapter_host", host),
                ("adapter_port", port), ("adapter_mode", mode)) if v is not None}
            new = VaultConfig(**{**old.model_dump(), **changes})
            validate_vault_entries([new if c.name == old.name else c for c in self.configs()])
            self._configs[old.name.lower()] = new
        self.reset(old.name)
        return new

    def is_started(self, name: str) -> bool:
        return self.config(name).name in self._services

    def start_default(self) -> VaultService:
        """Eagerly build the default vault so misconfiguration fails at launch, not mid-chat."""
        return self.get(self._default)

    def stop_all(self) -> None:
        with self._lock:
            services, self._services = list(self._services.items()), {}
        for name, svc in services:
            try:
                svc.stop()
            except Exception:  # pragma: no cover - best effort on shutdown
                logger.exception("Error stopping vault %r", name)

    # ------------------------------------------------------------------ #
    # Introspection (used by the vault_* tools and the server prompt)
    # ------------------------------------------------------------------ #

    def describe(self, name: str, *, probe: bool = False) -> dict[str, Any]:
        """Public info about one vault.  ``probe=True`` also starts it and counts files."""
        cfg = self.config(name)
        info: dict[str, Any] = {
            "name": cfg.name,
            "path": str(cfg.path),
            "description": cfg.description,
            "active": cfg.name == self._active,
            "started": cfg.name in self._services,
            "rest_key_set": bool(cfg.adapter_api_key),
            "rest_host": cfg.adapter_host,
            "rest_port": cfg.adapter_port,
            "adapter_mode": cfg.adapter_mode.value,
        }
        svc = self.get(cfg.name) if probe else self._services.get(cfg.name)
        if svc is not None:
            info["backend"] = getattr(getattr(svc, "_adapter", None), "backend_name", "unknown")
            try:
                info["file_count"] = len(svc.list_files())
            except Exception as exc:  # pragma: no cover - adapter specific
                info["error"] = f"{type(exc).__name__}: {exc}"
        return info

    def list(self) -> list[dict[str, Any]]:
        return [self.describe(n) for n in self._order]

    def prompt_block(self) -> str:
        """Paragraph for the server instructions so the model knows vaults exist and how to address them."""
        lines = [
            f"MULTIPLE VAULTS ({len(self)}). Vault at startup: {self._default!r} "
            "(call vault_list for the currently active one). Configured vaults:",
        ]
        for n in self._order:
            cfg = self.config(n)
            lines.append(f"  - {cfg.name}" + (f": {cfg.description}" if cfg.description else ""))
        lines.append(
            "Tools act on the active vault unless you pass vault='<name>' (works on every tool). "
            "Use vault_list to see vaults and vault_switch to change the active one. "
            "Tool results include a 'vault' field — check it before destructive operations, and "
            "always tell the user which vault you changed. Notes cannot be moved between vaults "
            "with move_note; copy content with read_note then create_note(vault=...)."
        )
        return "\n".join(lines)


class VaultRouter:
    """Looks like a ``VaultService``; forwards everything to the registry's current vault."""

    def __init__(self, registry: VaultRegistry) -> None:
        object.__setattr__(self, "_registry", registry)

    # Lifecycle is registry-wide, not "current vault only".
    def start(self) -> None:
        self._registry.start_default()

    def stop(self) -> None:
        self._registry.stop_all()

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):          # don't spin up a vault for dunder probes (copy, pickle, ...)
            raise AttributeError(name)
        return getattr(self._registry.current(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("VaultRouter is read-only; configure the underlying vault instead.")
