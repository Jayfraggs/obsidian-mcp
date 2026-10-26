"""Entry point for the Obsidian MCP server.

Usage:
    python -m obsidian_mcp           → MCP stdio server (for Claude Desktop)
    python -m obsidian_mcp web       → local Web UI
    python -m obsidian_mcp check     → validate config and exit
"""

from __future__ import annotations

import sys
import traceback


def _print_err(msg: str) -> None:
    """Write to stderr — the only channel Claude Desktop reads from the process."""
    print(msg, file=sys.stderr, flush=True)


def _build_vault_service():
    """Load settings, build adapter, return (settings, vault_service)."""
    from obsidian_mcp.adapters import AutoAdapter
    from obsidian_mcp.config import load_settings
    from obsidian_mcp.logging import configure_logging, get_logger
    from obsidian_mcp.vault.service import VaultService

    settings = load_settings()
    configure_logging(settings.log_level)
    logger = get_logger("main")

    logger.info("obsidian-mcp starting | vault=%s", settings.vault_path)

    adapter = AutoAdapter.from_settings(settings)
    logger.info("Adapter: %s", adapter.backend_name)

    vault_service = VaultService(settings.vault_path, adapter=adapter)
    return settings, vault_service, logger


def _load_runtime():
    """Return ``(settings, vault_service, registry, logger)``.

    One configured vault → exactly the legacy path (``registry`` is None).
    Several vaults → a ``VaultRegistry`` plus a ``VaultRouter`` that stands in for
    the vault service; only the default vault is started here, the rest start on
    first use so one offline Obsidian instance cannot block the server.
    """
    from obsidian_mcp.config import load_settings

    settings = load_settings()
    if len(getattr(settings, "vaults", ()) or ()) > 1:
        from obsidian_mcp.logging import configure_logging, get_logger
        from obsidian_mcp.vault.registry import VaultRegistry, VaultRouter

        configure_logging(settings.log_level)
        logger = get_logger("main")
        registry = VaultRegistry(settings.vaults, default=settings.default_vault)
        logger.info(
            "obsidian-mcp starting | %d vaults: %s | default=%s",
            len(registry), ", ".join(registry.names()), registry.default_name,
        )
        registry.start_default()
        return settings, VaultRouter(registry), registry, logger
    settings, vault_service, logger = _build_vault_service()
    return settings, vault_service, None, logger


def main() -> None:
    """Run the MCP stdio server (used by Claude Desktop and all MCP clients)."""
    try:
        from obsidian_mcp.server import create_server
        from obsidian_mcp.tools.core import register_core_tools
        from obsidian_mcp.tools.knowledge import register_knowledge_tools
        from obsidian_mcp.tools.plugins import register_plugin_tools
        from obsidian_mcp.web.app import _build_system_prompt, _load_rules

        settings, vault_service, registry, logger = _load_runtime()

        rules = _load_rules()
        rule_count = len(
            [line for line in rules.splitlines() if line.strip() and not line.startswith("#")]
        )
        logger.info("Loaded %d vault rules.", rule_count)
        system_prompt = _build_system_prompt(rules)

        server = create_server(
            settings,
            tool_registrars=(
                register_core_tools,
                register_knowledge_tools,
                register_plugin_tools,
            ),
            vault_service=vault_service,
            system_prompt=system_prompt,
            vault_registry=registry,
        )

        logger.info("Building backlink index and starting watcher …")
        vault_service.start()          # multi-vault: no-op for the already-started default vault

        logger.info("MCP server ready — waiting for client.")
        try:
            server.run()  # blocks on stdio
        finally:
            vault_service.stop()

    except KeyboardInterrupt:
        _print_err("[obsidian-mcp] Stopped.")
        sys.exit(0)

    except Exception as exc:
        # Print a clean error to stderr so Claude Desktop shows it in logs
        _print_err("\n[obsidian-mcp] STARTUP ERROR — server could not start.\n")
        _print_err(f"  {type(exc).__name__}: {exc}\n")

        # Common actionable hints
        msg = str(exc).lower()
        if "vault path" in msg or "does not exist" in msg:
            _print_err(
                "  -> Check OBSIDIAN_MCP_VAULT_PATH in your .env or claude_desktop_config.json"
            )
            _print_err("  -> Path must be absolute and must already exist")
        elif "no such file" in msg or "cannot find" in msg:
            _print_err("  -> A required file or directory was not found")
            _print_err("  -> Run: uv pip install -e . (from the obsidian-mcp project folder)")
        elif "permission" in msg or "access" in msg:
            _print_err("  -> Permission denied - check folder permissions on the vault")
        elif "adapter_api_key" in msg or "api_key" in msg:
            _print_err(
                "  -> REST API key issue - set OBSIDIAN_MCP_ADAPTER_MODE=filesystem to bypass"
            )
        elif "module" in msg or "import" in msg:
            _print_err("  -> Missing dependency - run: uv pip install -e .")

        _print_err("\nFull traceback:")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def web_main() -> None:
    """Run the local Web UI HTTP server."""
    try:
        import uvicorn

        from obsidian_mcp.web.app import create_web_app

        settings, vault_service, registry, logger = _load_runtime()
        logger.info("Building backlink index and starting watcher …")
        vault_service.start()
        logger.info("Web UI starting at http://%s:%s", settings.web_host, settings.web_port)

        try:
            uvicorn.run(
                create_web_app(settings, vault_service=vault_service, vault_registry=registry),
                host=settings.web_host,
                port=settings.web_port,
                log_level=settings.log_level.value.lower(),
            )
        finally:
            vault_service.stop()

    except KeyboardInterrupt:
        print("\n[obsidian-mcp-web] Stopped.", flush=True)
        sys.exit(0)

    except Exception as exc:
        _print_err(f"\n[obsidian-mcp-web] ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


def check_config() -> None:
    """Validate configuration and print a status report. Exits 0 on success."""
    try:
        from obsidian_mcp.config import load_settings
        settings = load_settings()
        print(f"[OK] vault_path:          {settings.vault_path}")
        print(f"[OK] adapter_mode:        {settings.adapter_mode.value}")
        print(f"[OK] permission_profile:  {settings.permission_profile.value}")
        print(f"[OK] templates_folder:    {settings.templates_folder}")
        print(f"[OK] web_port:            {settings.web_port}")
        api_key_status = "set" if settings.adapter_api_key else "not set (filesystem mode)"
        print(f"[OK] adapter_api_key:     {api_key_status}")

        vaults = list(getattr(settings, "vaults", ()) or ())
        if len(vaults) > 1:
            return _check_multi_vault(settings, vaults)

        from obsidian_mcp.adapters import AutoAdapter
        adapter = AutoAdapter.from_settings(settings)
        alive = adapter.health_check()
        adapter_status = "reachable" if alive else "ERROR: unreachable"
        print(f"[OK] adapter backend:     {adapter.backend_name} ({adapter_status})")

        if not alive:
            print("\n[ERROR] Vault is unreachable - check OBSIDIAN_MCP_VAULT_PATH")
            sys.exit(1)

        print("\nAll checks passed. Run with: python -m obsidian_mcp")
        sys.exit(0)

    except Exception as exc:
        print(f"\n[ERROR] Configuration error: {exc}")
        traceback.print_exc()
        sys.exit(1)


def _check_multi_vault(settings, vaults) -> None:
    """Report every configured vault and its own adapter.  Exits 1 if the default vault is unreachable."""
    from obsidian_mcp.adapters import AutoAdapter

    print(f"[OK] vaults configured:   {len(vaults)} (default: {settings.default_vault})")
    default_ok = True
    unreachable: list[str] = []
    for cfg in vaults:
        try:
            adapter = AutoAdapter.from_settings(cfg)
            alive = adapter.health_check()
            status = f"{adapter.backend_name} ({'reachable' if alive else 'ERROR: unreachable'})"
        except Exception as exc:           # a vault in rest-only mode whose Obsidian is closed
            alive, status = False, f"ERROR: {exc}"
        marker = "OK" if alive else "ERROR"
        key = "own REST key" if cfg.adapter_api_key else "no REST key (direct file access)"
        print(f"[{marker}] vault {cfg.name}: {cfg.path}")
        print(f"        adapter: {status}; {key}; mode={cfg.adapter_mode.value}")
        if not alive:
            unreachable.append(cfg.name)
        if cfg.name == settings.default_vault and not alive:
            default_ok = False
    if not default_ok:
        print("\n[ERROR] The default vault is unreachable - check its path / REST settings")
        sys.exit(1)
    if unreachable:
        print(f"\n[WARN] Default vault is fine, but not reachable: {', '.join(unreachable)}. "
              "The server will start; those vaults will report an error when used "
              "(open Obsidian with its Local REST API plugin, or fix the key/port).")
    else:
        print("\nAll checks passed.")
    print("Run with: python -m obsidian_mcp")
    sys.exit(0)


# ── Dispatcher ────────────────────────────────────────────────────────
# Supports both entry-point scripts and `python -m obsidian_mcp [mode]`

if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "mcp"
    if cmd == "web":
        web_main()
    elif cmd in ("check", "validate", "config"):
        check_config()
    elif cmd == "mcp":
        main()
    else:
        _print_err(f"Unknown command: {cmd}")
        _print_err("Usage: python -m obsidian_mcp [mcp|web|check]")
        sys.exit(1)
