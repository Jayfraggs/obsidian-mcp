"""
Obsidian MCP — Server Launcher
Runs the MCP server in the background and provides a system tray icon
with an openable status panel.

Usage:
    python server_launcher.py

This is the script the desktop shortcut points to after setup.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from datetime import datetime

# ── Bootstrap GUI/tray deps ───────────────────────────────────────────────
def _bootstrap_deps() -> None:
    missing = []
    for pkg, imp in [("customtkinter", "customtkinter"), ("pystray", "pystray"), ("Pillow", "PIL")]:
        try:
            __import__(imp)
        except ImportError:
            missing.append(pkg)
    if missing:
        print(f"Installing: {', '.join(missing)} …")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", *missing])

_bootstrap_deps()

import customtkinter as ctk          # noqa: E402
import pystray                        # noqa: E402
from PIL import Image, ImageDraw      # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────────

APP_TITLE   = "Obsidian MCP — Server Launcher"
ACCENT      = "#7C3AED"
SUCCESS     = "#16A34A"
ERROR_COL   = "#DC2626"
WARN        = "#D97706"
BG_CARD     = "#1E1E2E"
LOG_MAXLINES = 300

import os, shutil, platform  # noqa: E402


def get_os() -> str:
    s = platform.system()
    if s == "Windows": return "windows"
    if s == "Darwin":  return "mac"
    return "linux"


def get_project_root() -> Path:
    return Path(__file__).parent.resolve()


def get_uv_exe() -> str:
    return shutil.which("uv") or "uv"


def build_server_command() -> list[str]:
    return [get_uv_exe(), "--directory", str(get_project_root()), "run", "obsidian-mcp"]


# ── Tray icon image (drawn programmatically — no asset file needed) ───────

def _make_tray_image(color: str = "#7C3AED") -> Image.Image:
    img  = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Filled circle
    draw.ellipse([4, 4, 60, 60], fill=color)
    # Simple "M" mark for MCP
    draw.text((18, 18), "M", fill="white")
    return img


# ══════════════════════════════════════════════════════════════════════════
# Server process manager
# ══════════════════════════════════════════════════════════════════════════

class ServerProcess:
    """Manages the obsidian-mcp subprocess lifecycle."""

    def __init__(self, on_log, on_status_change) -> None:
        self._on_log            = on_log          # callable(str)
        self._on_status_change  = on_status_change # callable(str)  "running"|"stopped"|"error"
        self._proc: subprocess.Popen | None = None
        self._lock  = threading.Lock()
        self._status = "stopped"

    @property
    def status(self) -> str:
        return self._status

    def start(self) -> None:
        with self._lock:
            if self._proc and self._proc.poll() is None:
                self._log("Server is already running.")
                return
            cmd = build_server_command()
            self._log(f"Starting: {' '.join(cmd)}")
            try:
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=get_project_root(),
                )
                self._set_status("running")
                threading.Thread(target=self._stream_output, daemon=True).start()
                threading.Thread(target=self._watch_exit, daemon=True).start()
            except Exception as e:
                self._log(f"Failed to start: {e}")
                self._set_status("error")

    def stop(self) -> None:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._log("Server is not running.")
                return
            self._log("Stopping server …")
            try:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait()
                self._log("Server stopped.")
            except Exception as e:
                self._log(f"Error stopping server: {e}")
            finally:
                self._proc = None
                self._set_status("stopped")

    def restart(self) -> None:
        self.stop()
        time.sleep(0.5)
        self.start()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _stream_output(self) -> None:
        try:
            for line in self._proc.stdout:
                self._log(line.rstrip())
        except Exception:
            pass

    def _watch_exit(self) -> None:
        self._proc.wait()
        rc = self._proc.returncode
        if rc is not None and rc != 0:
            self._log(f"Server exited with code {rc}")
            self._set_status("error")
        elif self._status == "running":
            self._log("Server stopped unexpectedly.")
            self._set_status("stopped")

    def _log(self, msg: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._on_log(f"[{ts}] {msg}")

    def _set_status(self, status: str) -> None:
        self._status = status
        self._on_status_change(status)


# ══════════════════════════════════════════════════════════════════════════
# Status Panel (customtkinter window)
# ══════════════════════════════════════════════════════════════════════════

class StatusPanel(ctk.CTkToplevel):
    """Floating status window — opened from tray or at startup."""

    def __init__(self, server: ServerProcess) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.server = server
        self.title(APP_TITLE)
        self.geometry("560x420")
        self.resizable(True, True)
        self._center()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._refresh_status()

    def _center(self) -> None:
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - 560) // 2
        y = (self.winfo_screenheight() - 420) // 2
        self.geometry(f"+{x}+{y}")

    def _build_ui(self) -> None:
        # Header
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="Obsidian MCP",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=ACCENT,
        ).pack(side="left", padx=16, pady=16)

        self.status_badge = ctk.CTkLabel(
            header, text="● stopped",
            font=ctk.CTkFont(size=12),
            text_color="gray",
        )
        self.status_badge.pack(side="left", padx=8)

        # Controls
        ctrl = ctk.CTkFrame(self, corner_radius=0, height=52, fg_color="#16161E")
        ctrl.pack(fill="x")
        ctrl.pack_propagate(False)

        self.btn_start = ctk.CTkButton(
            ctrl, text="▶  Start", width=100,
            fg_color=SUCCESS, hover_color="#15803D",
            command=lambda: threading.Thread(target=self.server.start, daemon=True).start(),
        )
        self.btn_start.pack(side="left", padx=(12, 4), pady=10)

        self.btn_stop = ctk.CTkButton(
            ctrl, text="■  Stop", width=100,
            fg_color=ERROR_COL, hover_color="#B91C1C",
            command=lambda: threading.Thread(target=self.server.stop, daemon=True).start(),
        )
        self.btn_stop.pack(side="left", padx=4, pady=10)

        self.btn_restart = ctk.CTkButton(
            ctrl, text="↺  Restart", width=110,
            fg_color=WARN, hover_color="#B45309", text_color="black",
            command=lambda: threading.Thread(target=self.server.restart, daemon=True).start(),
        )
        self.btn_restart.pack(side="left", padx=4, pady=10)

        ctk.CTkButton(
            ctrl, text="Run Setup Again", width=130,
            fg_color="transparent", border_width=1,
            command=self._open_setup,
        ).pack(side="right", padx=12, pady=10)

        # Log box
        log_frame = ctk.CTkFrame(self, corner_radius=0)
        log_frame.pack(fill="both", expand=True, padx=0, pady=0)

        ctk.CTkLabel(
            log_frame, text="Server Log",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="gray",
        ).pack(anchor="w", padx=12, pady=(8, 0))

        self.log_box = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Courier", size=11),
            corner_radius=0,
        )
        self.log_box.pack(fill="both", expand=True, padx=0, pady=0)
        self.log_box.configure(state="disabled")

        # Footer
        footer = ctk.CTkFrame(self, corner_radius=0, height=32, fg_color=BG_CARD)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        root = get_project_root()
        ctk.CTkLabel(
            footer, text=str(root),
            font=ctk.CTkFont(size=10), text_color="gray",
        ).pack(side="left", padx=12)

    # ── Public API called from server process ──────────────────────────

    def append_log(self, msg: str) -> None:
        """Thread-safe log append."""
        self.after(0, lambda m=msg: self._append_log_main(m))

    def _append_log_main(self, msg: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        # Trim old lines
        lines = int(self.log_box.index("end-1c").split(".")[0])
        if lines > LOG_MAXLINES:
            self.log_box.delete("1.0", f"{lines - LOG_MAXLINES}.0")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def update_status(self, status: str) -> None:
        """Thread-safe status update."""
        self.after(0, lambda s=status: self._refresh_status(s))

    def _refresh_status(self, status: str | None = None) -> None:
        if status is None:
            status = self.server.status
        colors = {"running": SUCCESS, "stopped": "gray", "error": ERROR_COL}
        labels = {"running": "● running", "stopped": "● stopped", "error": "● error"}
        self.status_badge.configure(
            text=labels.get(status, status),
            text_color=colors.get(status, "gray"),
        )
        running = status == "running"
        self.btn_start.configure(state="disabled" if running else "normal")
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.btn_restart.configure(state="normal" if running else "disabled")

    def _on_close(self) -> None:
        """Hide instead of destroy — tray icon keeps app alive."""
        self.withdraw()

    def show(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def _open_setup(self) -> None:
        setup = get_project_root() / "setup_wizard.py"
        subprocess.Popen([sys.executable, str(setup)])


# ══════════════════════════════════════════════════════════════════════════
# Tray controller
# ══════════════════════════════════════════════════════════════════════════

class TrayController:
    """Owns the pystray icon and bridges it to the status panel."""

    def __init__(self, server: ServerProcess) -> None:
        self.server = server
        self.panel:  StatusPanel | None = None
        self._icon:  pystray.Icon | None = None
        self._root:  ctk.CTk | None = None   # hidden root needed for .after()

    def run(self) -> None:
        """Start everything. Blocks until quit."""
        # Hidden CTk root (required for Toplevel to work without a visible root)
        ctk.set_appearance_mode("dark")
        self._root = ctk.CTk()
        self._root.withdraw()

        # Wire server callbacks
        self.server._on_log           = self._on_log
        self.server._on_status_change = self._on_status_change

        # Build and show tray icon
        img  = _make_tray_image(ACCENT)
        menu = pystray.Menu(
            pystray.MenuItem("Obsidian MCP", lambda: None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Status Panel", self._open_panel, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Start Server",   lambda: threading.Thread(target=self.server.start,   daemon=True).start()),
            pystray.MenuItem("Stop Server",    lambda: threading.Thread(target=self.server.stop,    daemon=True).start()),
            pystray.MenuItem("Restart Server", lambda: threading.Thread(target=self.server.restart, daemon=True).start()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit",           self._quit),
        )
        self._icon = pystray.Icon("obsidian-mcp", img, "Obsidian MCP", menu)

        # Open panel immediately on first launch
        self._root.after(300, self._open_panel)

        # Auto-start server
        threading.Thread(target=self.server.start, daemon=True).start()

        # Run tray icon in background thread
        tray_thread = threading.Thread(target=self._icon.run, daemon=True)
        tray_thread.start()

        # Tkinter main loop
        self._root.mainloop()

    # ── Callbacks ─────────────────────────────────────────────────────

    def _on_log(self, msg: str) -> None:
        if self.panel:
            self.panel.append_log(msg)

    def _on_status_change(self, status: str) -> None:
        if self.panel:
            self.panel.update_status(status)
        # Update tray icon colour
        colors = {"running": SUCCESS, "stopped": "#6B7280", "error": ERROR_COL}
        color  = colors.get(status, "#6B7280")
        if self._icon:
            self._icon.icon = _make_tray_image(color)

    def _open_panel(self, *_) -> None:
        def _do():
            if self.panel is None or not self.panel.winfo_exists():
                self.panel = StatusPanel(self.server)
                self.panel.protocol("WM_DELETE_WINDOW", self.panel._on_close)
            else:
                self.panel.show()
        # Must run on the tkinter thread
        if self._root:
            self._root.after(0, _do)

    def _quit(self, *_) -> None:
        self.server.stop()
        if self._icon:
            self._icon.stop()
        if self._root:
            self._root.after(0, self._root.destroy)


# ══════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    server = ServerProcess(
        on_log=lambda msg: print(msg),           # overridden by TrayController
        on_status_change=lambda s: print(s),     # overridden by TrayController
    )
    tray = TrayController(server)
    tray.run()
