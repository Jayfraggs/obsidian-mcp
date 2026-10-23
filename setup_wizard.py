"""
Obsidian MCP — Setup Wizard
Cross-platform GUI setup wizard built with customtkinter.

Usage:
    python setup_wizard.py

Requires Python 3.11+. All other dependencies are installed automatically.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

# ── Bootstrap: install customtkinter if missing ────────────────────────────
def _bootstrap_deps() -> None:
    """Install GUI deps before importing them, with a plain-text progress indicator."""
    missing = []
    try:
        import customtkinter  # noqa: F401
    except ImportError:
        missing.append("customtkinter")
    try:
        import PIL  # noqa: F401
    except ImportError:
        missing.append("Pillow")

    if missing:
        print(f"Installing required GUI packages: {', '.join(missing)} …")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *missing]
        )
        print("Done. Starting wizard …\n")

_bootstrap_deps()

import customtkinter as ctk  # noqa: E402
from tkinter import filedialog, messagebox  # noqa: E402
from PIL import Image, ImageTk  # noqa: E402

# ── Constants ──────────────────────────────────────────────────────────────

APP_TITLE  = "Obsidian MCP — Setup Wizard"
APP_WIDTH  = 780
APP_HEIGHT = 620
ACCENT     = "#7C3AED"   # purple
SUCCESS    = "#16A34A"
WARN       = "#D97706"
ERROR_COL  = "#DC2626"
BG_CARD    = "#1E1E2E"

STEPS = [
    "Welcome",
    "Prerequisites",
    "REST API Setup",
    "Configure",
    "Environment",
    "Install",
    "Done",
]

REQUIRED_PYTHON = (3, 11)

# Plugin info shown on Prerequisites screen
REQUIRED_PLUGINS = [
    {
        "name": "Local REST API",
        "url": "https://github.com/coddingtonbear/obsidian-local-rest-api",
        "reason": "Required — allows this MCP to read and write your vault.",
    },
]

SUGGESTED_PLUGINS = [
    {"name": "Dataview",              "tools": "dataview_* tools — query notes as a database"},
    {"name": "Tasks",                 "tools": "tasks_* tools — manage tasks across your vault"},
    {"name": "Excalidraw",            "tools": "excalidraw_* tools — generate diagrams"},
    {"name": "Kanban",                "tools": "kanban_* tools — manage kanban boards"},
    {"name": "Templater",             "tools": "templater_* tools — apply templates to notes"},
    {"name": "Omnisearch",            "tools": "omnisearch_* tools — enhanced vault search"},
    {"name": "DataCharts",            "tools": "graph_datachart_* tools — line/bar/scatter/pie charts & equation plots",
     "url": "https://github.com/jcf-402/datacharts"},
    {"name": "Mathematica Plot",      "tools": "graph_mathematica_* tools — 2-D/3-D Wolfram Mathematica plots",
     "url": "https://github.com/marcosnicolau/obsidian-mathematica-plot"},
]

# ── OS helpers ─────────────────────────────────────────────────────────────

def get_os() -> str:
    s = platform.system()
    if s == "Windows": return "windows"
    if s == "Darwin":  return "mac"
    return "linux"


def get_claude_desktop_config_path() -> Path | None:
    os_name = get_os()
    if os_name == "windows":
        base = Path(os.environ.get("APPDATA", ""))
        return base / "Claude" / "claude_desktop_config.json"
    if os_name == "mac":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    # Linux
    xdg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return xdg / "Claude" / "claude_desktop_config.json"


def get_project_root() -> Path:
    """Directory containing setup_wizard.py == repo root."""
    return Path(__file__).parent.resolve()


def get_icon_path() -> Path:
    """Return the path to the bundled icon.png inside the package."""
    return get_project_root() / "src" / "obsidian_mcp" / "icon.png"


def get_env_path() -> Path:
    return get_project_root() / ".env"


def get_uv_exe() -> str | None:
    return shutil.which("uv")


def create_desktop_shortcut(server_mode: bool = False) -> bool:
    """Create a desktop shortcut to launch this wizard (or the server launcher).

    Returns True on success, False on failure.
    """
    os_name  = get_os()
    root     = get_project_root()
    py       = sys.executable
    script   = root / "setup_wizard.py"
    launcher = root / "server_launcher.py"
    target   = launcher if server_mode else script
    name     = "Obsidian MCP"
    desktop  = Path.home() / "Desktop"

    try:
        if os_name == "windows":
            lnk = desktop / f"{name}.lnk"
            _create_windows_shortcut(lnk, py, str(target), str(root))
        elif os_name == "mac":
            app = desktop / f"{name}.command"
            app.write_text(f'#!/bin/bash\ncd "{root}"\n"{py}" "{target}"\n')
            app.chmod(0o755)
        else:
            entry = desktop / f"{name}.desktop"
            entry.write_text(
                f"[Desktop Entry]\nType=Application\nName={name}\n"
                f"Exec={py} {target}\nPath={root}\nTerminal=false\n"
            )
            entry.chmod(0o755)
        return True
    except Exception:
        return False


def _create_windows_shortcut(lnk: Path, py: str, target: str, workdir: str) -> None:
    ps = (
        f'$ws = New-Object -ComObject WScript.Shell; '
        f'$s = $ws.CreateShortcut("{lnk}"); '
        f'$s.TargetPath = "{py}"; '
        f'$s.Arguments = "{target}"; '
        f'$s.WorkingDirectory = "{workdir}"; '
        f'$s.Save()'
    )
    subprocess.check_call(["powershell", "-Command", ps], timeout=15)


# ── .env writer ───────────────────────────────────────────────────────────

def write_env(fields: dict[str, str]) -> None:
    lines = [
        "# Obsidian MCP — generated by setup wizard",
        f"# Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for key, value in fields.items():
        lines.append(f"{key}={value}")
    get_env_path().write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Claude Desktop JSON merger ────────────────────────────────────────────

def merge_claude_desktop_config(server_command: list[str], env_vars: dict[str, str]) -> tuple[bool, str]:
    """Merge obsidian-mcp entry into Claude Desktop config. Returns (ok, message)."""
    cfg_path = get_claude_desktop_config_path()
    if cfg_path is None:
        return False, "Could not determine Claude Desktop config path for this OS."

    cfg_path.parent.mkdir(parents=True, exist_ok=True)

    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False, f"Existing config at {cfg_path} is not valid JSON. Fix it manually."
    else:
        cfg = {}

    cfg.setdefault("mcpServers", {})
    cfg["mcpServers"]["obsidian-mcp"] = {
        "command": server_command[0],
        "args":    server_command[1:],
        "env":     env_vars,
    }

    # Atomic write: write to .tmp then rename.
    tmp = cfg_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    tmp.replace(cfg_path)
    return True, str(cfg_path)


# ── uv installer ──────────────────────────────────────────────────────────

def install_uv() -> tuple[bool, str]:
    """Install uv via the official installer. Returns (ok, output)."""
    os_name = get_os()
    try:
        if os_name == "windows":
            cmd = [
                "powershell", "-ExecutionPolicy", "Bypass", "-Command",
                "irm https://astral.sh/uv/install.ps1 | iex"
            ]
        else:
            cmd = ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            return True, result.stdout
        return False, result.stderr
    except Exception as e:
        return False, str(e)


def run_uv_sync(log_callback) -> tuple[bool, str]:
    """Run `uv sync` in the project root. Streams output via log_callback."""
    root = get_project_root()
    uv   = get_uv_exe() or "uv"
    try:
        proc = subprocess.Popen(
            [uv, "sync"],
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        output_lines = []
        for line in proc.stdout:
            line = line.rstrip()
            output_lines.append(line)
            log_callback(line)
        proc.wait()
        full = "\n".join(output_lines)
        return proc.returncode == 0, full
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════════════════════════
# GUI — Main wizard window
# ══════════════════════════════════════════════════════════════════════════

class SetupWizard(ctk.CTk):

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)
        self.geometry(f"{APP_WIDTH}x{APP_HEIGHT}")
        self.resizable(False, False)
        self._set_icon()
        self._center_window()

        # State
        self.current_step = 0
        self.fields: dict[str, ctk.StringVar] = {}
        self.booleans: dict[str, ctk.BooleanVar] = {}
        self._setup_state_vars()

        # Layout: left sidebar + right content
        self._build_sidebar()
        self._build_content_area()
        self._show_step(0)

    # ── Window helpers ─────────────────────────────────────────────────

    def _center_window(self) -> None:
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - APP_WIDTH)  // 2
        y = (self.winfo_screenheight() - APP_HEIGHT) // 2
        self.geometry(f"+{x}+{y}")

    def _set_icon(self) -> None:
        """Set the window icon from the bundled assets.

        Windows uses a multi-resolution .ico file via iconbitmap(); other
        platforms use wm_iconphoto() with the PNG.  Both paths are wrapped
        in try/except — icon loading is cosmetic and must never crash the wizard.
        """
        try:
            if get_os() == "windows":
                ico = get_project_root() / "src" / "obsidian_mcp" / "icon.ico"
                if ico.exists():
                    self.iconbitmap(default=str(ico))
            else:
                png = get_icon_path()
                if png.exists():
                    img = Image.open(png)
                    # Hold a reference — ImageTk.PhotoImage is GC'd without one
                    self._icon_image = ImageTk.PhotoImage(img)
                    self.wm_iconphoto(True, self._icon_image)
        except Exception:
            pass  # Never crash the wizard over a cosmetic feature

    # ── State vars ─────────────────────────────────────────────────────

    def _setup_state_vars(self) -> None:
        v = self.fields
        b = self.booleans
        v["vault_path"]        = ctk.StringVar()
        v["server_name"]       = ctk.StringVar(value="obsidian-mcp")
        v["log_level"]         = ctk.StringVar(value="INFO")
        v["permission_profile"]= ctk.StringVar(value="safe_write")
        v["adapter_mode"]      = ctk.StringVar(value="auto")
        v["adapter_api_key"]   = ctk.StringVar()
        v["adapter_host"]      = ctk.StringVar(value="127.0.0.1")
        v["adapter_port"]      = ctk.StringVar(value="27123")
        v["web_host"]          = ctk.StringVar(value="127.0.0.1")
        v["web_port"]          = ctk.StringVar(value="8765")
        v["templates_folder"]  = ctk.StringVar(value="Templates")
        b["enable_web_ui"]     = ctk.BooleanVar(value=False)
        b["add_claude_desktop"]= ctk.BooleanVar(value=True)
        b["create_shortcut"]   = ctk.BooleanVar(value=True)
        b["prerequisites_ack"] = ctk.BooleanVar(value=False)

    # ── Layout ─────────────────────────────────────────────────────────

    def _build_sidebar(self) -> None:
        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0, fg_color=BG_CARD)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        ctk.CTkLabel(
            self.sidebar, text="Obsidian MCP",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=ACCENT,
        ).pack(pady=(24, 4), padx=16, anchor="w")

        ctk.CTkLabel(
            self.sidebar, text="Setup Wizard",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        ).pack(padx=16, anchor="w")

        ctk.CTkFrame(self.sidebar, height=1, fg_color="#333").pack(
            fill="x", padx=16, pady=16
        )

        self._step_labels: list[ctk.CTkLabel] = []
        for i, step in enumerate(STEPS):
            lbl = ctk.CTkLabel(
                self.sidebar,
                text=f"  {i + 1}. {step}",
                font=ctk.CTkFont(size=12),
                anchor="w",
                text_color="gray",
            )
            lbl.pack(fill="x", padx=8, pady=2)
            self._step_labels.append(lbl)

    def _build_content_area(self) -> None:
        self.content = ctk.CTkFrame(self, corner_radius=0)
        self.content.pack(side="right", fill="both", expand=True)

        self.page_frame = ctk.CTkScrollableFrame(self.content, corner_radius=0)
        self.page_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Nav buttons at bottom
        nav = ctk.CTkFrame(self.content, height=60, corner_radius=0, fg_color=BG_CARD)
        nav.pack(side="bottom", fill="x")
        nav.pack_propagate(False)

        self.btn_back = ctk.CTkButton(
            nav, text="← Back", width=100,
            fg_color="transparent", border_width=1,
            command=self._go_back,
        )
        self.btn_back.pack(side="left", padx=16, pady=12)

        self.btn_next = ctk.CTkButton(
            nav, text="Next →", width=120,
            fg_color=ACCENT, hover_color="#6D28D9",
            command=self._go_next,
        )
        self.btn_next.pack(side="right", padx=16, pady=12)

    # ── Step navigation ────────────────────────────────────────────────

    def _show_step(self, index: int) -> None:
        self.current_step = index
        # Update sidebar
        for i, lbl in enumerate(self._step_labels):
            if i == index:
                lbl.configure(text_color="white",
                               font=ctk.CTkFont(size=12, weight="bold"))
            elif i < index:
                lbl.configure(text_color=SUCCESS)
            else:
                lbl.configure(text_color="gray",
                               font=ctk.CTkFont(size=12))

        # Clear page
        for w in self.page_frame.winfo_children():
            w.destroy()

        # Nav state
        self.btn_back.configure(state="normal" if index > 0 else "disabled")
        is_last = index == len(STEPS) - 1
        self.btn_next.configure(
            text="Close" if is_last else "Next →",
            command=self.destroy if is_last else self._go_next,
        )

        # Render page
        pages = [
            self._page_welcome,
            self._page_prerequisites,
            self._page_rest_api,
            self._page_configure,
            self._page_environment,
            self._page_install,
            self._page_done,
        ]
        pages[index]()

    def _go_next(self) -> None:
        if not self._validate_step():
            return
        if self.current_step < len(STEPS) - 1:
            self._show_step(self.current_step + 1)

    def _go_back(self) -> None:
        if self.current_step > 0:
            self._show_step(self.current_step - 1)

    # ── Validation ─────────────────────────────────────────────────────

    def _validate_step(self) -> bool:
        step = self.current_step

        if step == 1:  # Prerequisites
            if not self.booleans["prerequisites_ack"].get():
                messagebox.showwarning(
                    "Acknowledgement required",
                    "Please confirm you have installed the Local REST API plugin before continuing.",
                )
                return False

        if step == 3:  # Configure
            vault = self.fields["vault_path"].get().strip()
            if not vault:
                messagebox.showwarning("Vault path required", "Please select your Obsidian vault folder.")
                return False
            if not Path(vault).is_dir():
                messagebox.showwarning("Invalid path", f"'{vault}' is not a valid directory.")
                return False

            mode = self.fields["adapter_mode"].get()
            if mode in ("auto", "rest"):
                key = self.fields["adapter_api_key"].get().strip()
                if not key:
                    messagebox.showwarning(
                        "API key required",
                        "Adapter mode is set to REST/Auto — an API key is required.\n"
                        "Switch to 'filesystem' mode if you don't have one yet.",
                    )
                    return False

        return True

    # ══════════════════════════════════════════════════════════════════
    # Pages
    # ══════════════════════════════════════════════════════════════════

    def _page_welcome(self) -> None:
        f = self.page_frame
        _heading(f, "Welcome to Obsidian MCP Setup")
        _body(f,
            "This wizard will guide you through configuring the Obsidian MCP server "
            "so you can connect your Obsidian vault to any MCP-compatible AI client "
            "(Claude Desktop, Cursor, Windsurf, and others).\n\n"
            "The wizard will:\n"
            "  • Install uv (if not already installed)\n"
            "  • Create your .env configuration file\n"
            "  • Optionally configure Claude Desktop\n"
            "  • Install all dependencies\n"
            "  • Create a desktop shortcut\n\n"
            "Click Next to begin."
        )

        # Python version check
        pv = sys.version_info
        ok = pv >= REQUIRED_PYTHON
        status_text = f"Python {pv.major}.{pv.minor}.{pv.micro} {'✓' if ok else '✗ (3.11+ required)'}"
        _status_badge(f, status_text, ok)

        # uv check
        uv = get_uv_exe()
        uv_text = f"uv {'found: ' + uv if uv else 'not found — will be installed automatically'}"
        _status_badge(f, uv_text, uv is not None)

    def _page_prerequisites(self) -> None:
        f = self.page_frame
        _heading(f, "Prerequisites")
        _body(f, "Before using Obsidian MCP you need the following Obsidian plugin installed and configured.")

        # Required
        ctk.CTkLabel(f, text="Required Plugin", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=ERROR_COL).pack(anchor="w", padx=24, pady=(16, 4))

        for p in REQUIRED_PLUGINS:
            card = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=8)
            card.pack(fill="x", padx=24, pady=4)
            ctk.CTkLabel(card, text=p["name"],
                         font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=12, pady=(10, 0))
            ctk.CTkLabel(card, text=p["reason"],
                         text_color="gray", wraplength=480, justify="left").pack(anchor="w", padx=12, pady=(0, 4))
            ctk.CTkLabel(card, text=p["url"], text_color="#818CF8",
                         cursor="hand2").pack(anchor="w", padx=12, pady=(0, 10))

        # Suggested
        ctk.CTkLabel(f, text="Suggested Plugins (optional)",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=WARN).pack(anchor="w", padx=24, pady=(20, 4))
        _body(f, "Install these to unlock additional MCP tools:", pady=0)

        for p in SUGGESTED_PLUGINS:
            row = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=8)
            row.pack(fill="x", padx=24, pady=3)
            ctk.CTkLabel(row, text=f"  {p['name']}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         width=140, anchor="w").pack(side="left", padx=8, pady=8)
            text_col = ctk.CTkFrame(row, fg_color="transparent")
            text_col.pack(side="left", padx=8, pady=4, fill="x", expand=True)
            ctk.CTkLabel(text_col, text=p["tools"], text_color="gray",
                         anchor="w", justify="left").pack(anchor="w")
            if p.get("url"):
                ctk.CTkLabel(text_col, text=p["url"], text_color="#818CF8",
                             cursor="hand2", anchor="w",
                             font=ctk.CTkFont(size=11)).pack(anchor="w")

        # Acknowledgement
        ctk.CTkFrame(f, height=1, fg_color="#444").pack(fill="x", padx=24, pady=16)
        ctk.CTkCheckBox(
            f,
            text="I have installed the Local REST API plugin in Obsidian",
            variable=self.booleans["prerequisites_ack"],
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=24, pady=4)

    def _page_rest_api(self) -> None:
        f = self.page_frame
        _heading(f, "Local REST API — Setup Guide")
        _body(f,
            "The Local REST API plugin is required for the MCP to communicate with your vault. "
            "Follow these steps inside Obsidian:"
        )

        steps_text = [
            ("Step 1", "Open Obsidian → Settings (gear icon, bottom left)"),
            ("Step 2", "Go to Community Plugins → Browse"),
            ("Step 3", "Search for 'Local REST API' and install it"),
            ("Step 4", "Enable the plugin, then click the plugin's settings icon"),
            ("Step 5", "Note the API Key shown — you'll need it in the next screen"),
            ("Step 6", "Note the Port (default: 27123) — ensure it matches what you'll enter"),
            ("Step 7", "Make sure 'Enable' is toggled ON in the plugin settings"),
        ]

        for title, desc in steps_text:
            row = ctk.CTkFrame(f, fg_color=BG_CARD, corner_radius=8)
            row.pack(fill="x", padx=24, pady=3)
            ctk.CTkLabel(row, text=title, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=ACCENT, width=70, anchor="w").pack(
                side="left", padx=(12, 4), pady=10)
            ctk.CTkLabel(row, text=desc, anchor="w", justify="left",
                         wraplength=500).pack(side="left", padx=4, pady=10)

        _body(f,
            "\nIf you plan to use filesystem mode only (no REST API plugin), "
            "you can skip entering an API key on the next screen and set adapter mode to 'filesystem'.",
            text_color="gray",
        )

    def _page_configure(self) -> None:
        f = self.page_frame
        _heading(f, "Configure")
        _body(f, "Fill in the settings below. These will be saved to your .env file.")

        # ── Vault path ──
        _section(f, "Vault")
        _field_row(f, "Vault Path *", self.fields["vault_path"],
                   browse=lambda: self._browse_folder("vault_path"),
                   hint="Absolute path to your Obsidian vault folder")

        # ── Server ──
        _section(f, "Server")
        _field_row(f, "Server Name", self.fields["server_name"],
                   hint="Identifier shown to MCP clients")
        _dropdown_row(f, "Log Level", self.fields["log_level"],
                      ["DEBUG", "INFO", "WARNING", "ERROR"])
        _dropdown_row(f, "Permission Profile", self.fields["permission_profile"],
                      ["read_only", "safe_write", "admin"],
                      hint="read_only: read only · safe_write: read + write (recommended) · admin: full access")

        # ── Adapter ──
        _section(f, "Adapter")
        adapter_var = self.fields["adapter_mode"]
        _dropdown_row(f, "Adapter Mode", adapter_var,
                      ["auto", "rest", "filesystem"],
                      hint="auto: tries REST then falls back to filesystem · rest: REST only · filesystem: direct disk access")

        api_frame = ctk.CTkFrame(f, fg_color="transparent")
        api_frame.pack(fill="x", padx=24, pady=2)

        def _update_api_fields(*_):
            mode = adapter_var.get()
            state = "disabled" if mode == "filesystem" else "normal"
            for w in api_frame.winfo_children():
                try: w.configure(state=state)
                except Exception: pass

        adapter_var.trace_add("write", _update_api_fields)

        _field_row(api_frame, "API Key", self.fields["adapter_api_key"],
                   hint="From Obsidian → Local REST API plugin settings", password=True)
        _field_row(api_frame, "Adapter Host", self.fields["adapter_host"])
        _field_row(api_frame, "Adapter Port", self.fields["adapter_port"])
        _update_api_fields()

        # ── Templates ──
        _section(f, "Templates")
        _field_row(f, "Templates Folder", self.fields["templates_folder"],
                   hint="Vault-relative folder for Templater templates")

        # ── Web UI ──
        _section(f, "Web UI (optional)")
        web_toggle = ctk.CTkCheckBox(
            f, text="Enable Web UI",
            variable=self.booleans["enable_web_ui"],
        )
        web_toggle.pack(anchor="w", padx=24, pady=4)

        web_frame = ctk.CTkFrame(f, fg_color="transparent")
        web_frame.pack(fill="x", padx=24)

        def _update_web_fields(*_):
            state = "normal" if self.booleans["enable_web_ui"].get() else "disabled"
            for w in web_frame.winfo_children():
                try: w.configure(state=state)
                except Exception: pass

        self.booleans["enable_web_ui"].trace_add("write", _update_web_fields)
        _field_row(web_frame, "Web Host", self.fields["web_host"])
        _field_row(web_frame, "Web Port", self.fields["web_port"])
        _update_web_fields()

        # ── Claude Desktop ──
        _section(f, "Claude Desktop (optional)")
        cfg_path = get_claude_desktop_config_path()
        hint = f"Will merge into: {cfg_path}" if cfg_path else "Claude Desktop not detected on this OS"
        ctk.CTkCheckBox(
            f,
            text=f"Add to Claude Desktop config  —  {hint}",
            variable=self.booleans["add_claude_desktop"],
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=24, pady=4)

        # ── Shortcut ──
        _section(f, "Desktop Shortcut")
        ctk.CTkCheckBox(
            f,
            text="Create a desktop shortcut to launch the server",
            variable=self.booleans["create_shortcut"],
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=24, pady=4)

    def _page_environment(self) -> None:
        """Preview of the .env that will be written."""
        f = self.page_frame
        _heading(f, "Review Configuration")
        _body(f, "The following will be written to your .env file. Click Next to proceed.")

        env_dict = self._build_env_dict()
        preview = "\n".join(f"{k}={v}" for k, v in env_dict.items())

        box = ctk.CTkTextbox(f, height=260, font=ctk.CTkFont(family="Courier", size=12))
        box.pack(fill="x", padx=24, pady=12)
        box.insert("1.0", preview)
        box.configure(state="disabled")

        if self.booleans["add_claude_desktop"].get():
            _body(f, "Claude Desktop config will also be updated (merge-safe).", text_color=SUCCESS)

        server_cmd = self._build_server_command()
        _body(f, "\nServer command that will be registered:")
        cmd_box = ctk.CTkTextbox(f, height=60, font=ctk.CTkFont(family="Courier", size=11))
        cmd_box.pack(fill="x", padx=24, pady=4)
        cmd_box.insert("1.0", " ".join(server_cmd))
        cmd_box.configure(state="disabled")

    def _page_install(self) -> None:
        f = self.page_frame
        _heading(f, "Installing")
        _body(f, "Please wait while the setup completes …")

        self.log_box = ctk.CTkTextbox(
            f, height=320, font=ctk.CTkFont(family="Courier", size=11)
        )
        self.log_box.pack(fill="x", padx=24, pady=12)

        self.btn_next.configure(state="disabled")
        self.btn_back.configure(state="disabled")

        threading.Thread(target=self._run_install, daemon=True).start()

    def _run_install(self) -> None:
        def log(msg: str) -> None:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")

        errors = []

        # 1. Install uv if missing
        if not get_uv_exe():
            log("→ uv not found — installing …")
            ok, out = install_uv()
            if ok:
                log("✓ uv installed successfully")
            else:
                log(f"✗ uv install failed: {out}")
                errors.append("uv installation failed")
        else:
            log(f"✓ uv found: {get_uv_exe()}")

        # 2. Write .env
        log("\n→ Writing .env …")
        try:
            write_env(self._build_env_dict())
            log(f"✓ .env written to {get_env_path()}")
        except Exception as e:
            log(f"✗ Failed to write .env: {e}")
            errors.append(f".env write failed: {e}")

        # 3. Claude Desktop merge
        if self.booleans["add_claude_desktop"].get():
            log("\n→ Updating Claude Desktop config …")
            server_cmd = self._build_server_command()
            env_vars   = self._build_env_dict()
            ok, msg = merge_claude_desktop_config(server_cmd, env_vars)
            if ok:
                log(f"✓ Claude Desktop config updated: {msg}")
            else:
                log(f"✗ Claude Desktop config error: {msg}")
                errors.append(f"Claude Desktop config: {msg}")

        # 4. uv sync
        log("\n→ Running uv sync (installing dependencies) …")
        ok, _ = run_uv_sync(log)
        if ok:
            log("✓ Dependencies installed")
        else:
            log("✗ uv sync failed — check output above")
            errors.append("uv sync failed")

        # 5. Desktop shortcut
        if self.booleans["create_shortcut"].get():
            log("\n→ Creating desktop shortcut …")
            ok = create_desktop_shortcut(server_mode=True)
            if ok:
                log("✓ Desktop shortcut created")
            else:
                log("✗ Could not create shortcut (non-fatal — you can run manually)")

        # Done
        self._install_errors = errors
        log("\n" + ("━" * 50))
        if errors:
            log(f"⚠  Setup completed with {len(errors)} issue(s). See above.")
        else:
            log("✓  Setup complete!")

        self.after(0, lambda: self.btn_next.configure(state="normal"))
        self.after(0, lambda: self._show_step(len(STEPS) - 1))

    def _page_done(self) -> None:
        f = self.page_frame
        errors = getattr(self, "_install_errors", [])

        if errors:
            _heading(f, "Setup Complete (with warnings)")
            _body(f, "Setup finished but there were some issues:", text_color=WARN)
            for e in errors:
                ctk.CTkLabel(f, text=f"  • {e}", text_color=ERROR_COL).pack(
                    anchor="w", padx=32)
        else:
            _heading(f, "✓ Setup Complete!")
            _body(f, "Everything is configured and ready to use.")

        _section(f, "Server Command")
        cmd_str = " ".join(self._build_server_command())
        cmd_box = ctk.CTkTextbox(f, height=56, font=ctk.CTkFont(family="Courier", size=11))
        cmd_box.pack(fill="x", padx=24, pady=4)
        cmd_box.insert("1.0", cmd_str)
        cmd_box.configure(state="disabled")

        ctk.CTkButton(
            f, text="Copy Server Command",
            fg_color="transparent", border_width=1,
            command=lambda: self._copy_to_clipboard(cmd_str),
        ).pack(anchor="w", padx=24, pady=4)

        _section(f, "What's next?")
        _body(f,
            "• Paste the server command into your MCP client (Cursor, Windsurf, etc.)\n"
            "• If you added Claude Desktop support, restart Claude Desktop\n"
            "• Use the desktop shortcut to start the server at any time\n"
            "• Run  uv run obsidian-mcp check  in this folder to verify your config"
        )

        ctk.CTkButton(
            f, text="Launch Server Now",
            fg_color=SUCCESS, hover_color="#15803D",
            command=self._launch_server,
        ).pack(anchor="w", padx=24, pady=(16, 4))

    # ── Helpers ────────────────────────────────────────────────────────

    def _browse_folder(self, field_key: str) -> None:
        path = filedialog.askdirectory(title="Select your Obsidian vault folder")
        if path:
            self.fields[field_key].set(path)

    def _copy_to_clipboard(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Server command copied to clipboard.")

    def _build_env_dict(self) -> dict[str, str]:
        v = self.fields
        b = self.booleans
        d: dict[str, str] = {
            "OBSIDIAN_MCP_VAULT_PATH":         v["vault_path"].get(),
            "OBSIDIAN_MCP_SERVER_NAME":        v["server_name"].get(),
            "OBSIDIAN_MCP_LOG_LEVEL":          v["log_level"].get(),
            "OBSIDIAN_MCP_PERMISSION_PROFILE": v["permission_profile"].get(),
            "OBSIDIAN_MCP_ADAPTER_MODE":       v["adapter_mode"].get(),
            "OBSIDIAN_MCP_ADAPTER_HOST":       v["adapter_host"].get(),
            "OBSIDIAN_MCP_ADAPTER_PORT":       v["adapter_port"].get(),
            "OBSIDIAN_MCP_TEMPLATES_FOLDER":   v["templates_folder"].get(),
        }
        key = v["adapter_api_key"].get().strip()
        if key:
            d["OBSIDIAN_MCP_ADAPTER_API_KEY"] = key
        if b["enable_web_ui"].get():
            d["OBSIDIAN_MCP_WEB_HOST"] = v["web_host"].get()
            d["OBSIDIAN_MCP_WEB_PORT"] = v["web_port"].get()
        return d

    def _build_server_command(self) -> list[str]:
        uv  = get_uv_exe() or "uv"
        root = str(get_project_root())
        return [uv, "--directory", root, "run", "obsidian-mcp"]

    def _launch_server(self) -> None:
        cmd = self._build_server_command()
        try:
            if get_os() == "windows":
                subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                subprocess.Popen(cmd)
            messagebox.showinfo("Server Started", "Obsidian MCP server is starting in the background.")
        except Exception as e:
            messagebox.showerror("Launch Failed", str(e))


# ══════════════════════════════════════════════════════════════════════════
# GUI widget helpers (keep pages readable)
# ══════════════════════════════════════════════════════════════════════════

def _heading(parent, text: str) -> None:
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=20, weight="bold"),
        anchor="w",
    ).pack(anchor="w", padx=24, pady=(24, 4))
    ctk.CTkFrame(parent, height=1, fg_color="#444").pack(fill="x", padx=24, pady=(0, 12))


def _body(parent, text: str, text_color: str = "gray70",
          pady: int = 4) -> None:
    ctk.CTkLabel(
        parent, text=text,
        text_color=text_color,
        wraplength=520,
        justify="left",
        anchor="w",
    ).pack(anchor="w", padx=24, pady=pady)


def _section(parent, text: str) -> None:
    ctk.CTkLabel(
        parent, text=text,
        font=ctk.CTkFont(size=13, weight="bold"),
        text_color="white",
        anchor="w",
    ).pack(anchor="w", padx=24, pady=(16, 2))


def _status_badge(parent, text: str, ok: bool) -> None:
    color = SUCCESS if ok else ERROR_COL
    ctk.CTkLabel(
        parent, text=f"  {'✓' if ok else '✗'}  {text}",
        text_color=color,
        font=ctk.CTkFont(size=12),
        anchor="w",
    ).pack(anchor="w", padx=24, pady=2)


def _field_row(
    parent,
    label: str,
    var: ctk.StringVar,
    browse=None,
    hint: str = "",
    password: bool = False,
) -> None:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=24, pady=3)

    ctk.CTkLabel(row, text=label, width=160, anchor="w",
                 font=ctk.CTkFont(size=12)).pack(side="left")

    entry = ctk.CTkEntry(
        row, textvariable=var, width=260,
        show="•" if password else "",
    )
    entry.pack(side="left", padx=(0, 6))

    if browse:
        ctk.CTkButton(row, text="Browse …", width=80,
                      fg_color="transparent", border_width=1,
                      command=browse).pack(side="left")

    if hint:
        ctk.CTkLabel(row, text=hint, text_color="gray", font=ctk.CTkFont(size=10)).pack(
            side="left", padx=8)


def _dropdown_row(
    parent,
    label: str,
    var: ctk.StringVar,
    values: list[str],
    hint: str = "",
) -> None:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=24, pady=3)

    ctk.CTkLabel(row, text=label, width=160, anchor="w",
                 font=ctk.CTkFont(size=12)).pack(side="left")

    ctk.CTkOptionMenu(row, variable=var, values=values, width=200).pack(
        side="left", padx=(0, 6))

    if hint:
        ctk.CTkLabel(row, text=hint, text_color="gray",
                     font=ctk.CTkFont(size=10), wraplength=240).pack(
            side="left", padx=8)


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = SetupWizard()
    app.mainloop()
