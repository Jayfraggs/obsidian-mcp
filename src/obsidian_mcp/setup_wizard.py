"""
Obsidian MCP — Setup Wizard (moved into package for packaging)
"""

from __future__ import annotations

import subprocess
import sys
import shutil
import platform
from pathlib import Path

def get_os() -> str:
    s = platform.system()
    if s == "Windows": return "windows"
    if s == "Darwin":  return "mac"
    return "linux"

def get_project_root() -> Path:
    # When installed inside src/, repo root is two parents up.
    return Path(__file__).resolve().parents[2]

def get_icon_path() -> Path:
    return get_project_root() / "src" / "obsidian_mcp" / "icon.png"

def get_env_path() -> Path:
    return get_project_root() / ".env"

def _bootstrap_deps() -> None:
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter"])

_bootstrap_deps()

if __name__ == "__main__":
    print("Setup wizard moved into package; run via source repository or use packaging entry points.")
