"""Multi-vault MCP tooling.

* ``vault_list`` / ``vault_switch`` / ``vault_status`` – see and change vaults.
* :class:`VaultAwareServer` – wraps the FastMCP server handed to the tool
  registrars so that **every** tool gains an optional ``vault`` argument and
  every ``dict`` result is stamped with the vault it ran on.  No tool body has
  to know about vaults.
"""

from __future__ import annotations

import functools
import inspect
from typing import Annotated, Any, Callable

from pydantic import Field

from obsidian_mcp.vault.registry import VaultRegistry

VAULT_TOOL_NAMES = ("vault_list", "vault_switch", "vault_status")

_VAULT_ARG_DOC = "Vault to run this on (see vault_list). Default: the active vault."


def add_vault_param(fn: Callable[..., Any], registry: VaultRegistry) -> Callable[..., Any]:
    """Return *fn* wrapped to accept ``vault=`` and to report which vault it used."""
    sig = inspect.signature(fn, eval_str=True)          # resolve string annotations in fn's own module
    if "vault" in sig.parameters:                         # tool already manages vaults itself
        return fn

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        vault = kwargs.pop("vault", None)
        with registry.use(vault) as cfg:
            result = fn(*args, **kwargs)
            if isinstance(result, dict) and "vault" not in result:
                result = {**result, "vault": cfg.name}
            return result

    params = list(sig.parameters.values())
    params.append(inspect.Parameter(
        "vault", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None,
        annotation=Annotated[str | None, Field(description=_VAULT_ARG_DOC)],
    ))
    wrapper.__signature__ = sig.replace(parameters=params)  # type: ignore[attr-defined]
    wrapper.__annotations__ = {p.name: p.annotation for p in params}
    if sig.return_annotation is not inspect.Signature.empty:
        wrapper.__annotations__["return"] = sig.return_annotation
    return wrapper


class VaultAwareServer:
    """Proxy around a FastMCP server: ``.tool(name)`` adds the ``vault`` argument."""

    def __init__(self, inner: Any, registry: VaultRegistry) -> None:
        self._inner = inner
        self._registry = registry

    def tool(self, *args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        register = self._inner.tool(*args, **kwargs)

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            register(add_vault_param(fn, self._registry))
            return fn                                        # callers keep the original function

        return decorator

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def register_vault_tools(server: Any, registry: VaultRegistry) -> None:
    """Register ``vault_list`` / ``vault_switch`` / ``vault_status`` on the raw server."""

    @server.tool("vault_list")
    def vault_list() -> dict[str, Any]:
        """List the configured vaults and which one is active."""
        return {"active": registry.active_name, "vaults": registry.list()}

    @server.tool("vault_switch")
    def vault_switch(name: str) -> dict[str, Any]:
        """Make `name` the active vault for the rest of this session.

        Prefer passing vault='<name>' on a single tool call for one-off access
        to another vault — switching changes where every later call lands.
        """
        previous = registry.active_name
        registry.set_active(name)
        info = registry.describe(registry.active_name, probe=True)
        return {"previous": previous, **info}

    @server.tool("vault_status")
    def vault_status(name: str | None = None) -> dict[str, Any]:
        """Health and size of a vault (default: the active one). Starts the vault if needed."""
        return registry.describe(name or registry.active_name, probe=True)
