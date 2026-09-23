"""Optional KiCad source adapter for the CAD-neutral SPIKE desktop application.

The module is intentionally safe to import in normal Python environments. KiCad
objects are resolved only when the adapter is loaded by pcbnew. Product commands,
projects, and solver contracts remain vendor-neutral.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

try:  # pcbnew and wx exist only inside KiCad's Python process.
    import pcbnew  # type: ignore
    import wx  # type: ignore
except ImportError:  # pragma: no cover - exercised by normal Python imports
    pcbnew = None
    wx = None


BRIDGE_VERSION = "spike-bridge/v1"


def build_context(board_path: str = "", selected_nets: list[str] | None = None,
                  selected_components: list[str] | None = None) -> Dict[str, Any]:
    return {
        "contract": BRIDGE_VERSION,
        "board_path": str(Path(board_path).resolve()) if board_path else "",
        "selected_nets": selected_nets or [],
        "selected_components": selected_components or [],
        "coordinate_system": "board-mm",
    }


def write_context(context: Dict[str, Any]) -> Path:
    path = Path(tempfile.gettempdir()) / f"spike-context-{os.getpid()}.json"
    path.write_text(json.dumps(context, indent=2), encoding="utf-8")
    return path


def find_desktop_executable() -> str | None:
    candidates = [
        shutil.which("spike-desktop"),
        str(Path(__file__).parent.parent / "app" / "src-tauri" / "target" / "release" / "spike-desktop.exe"),
        str(Path(__file__).parent.parent / "dist" / "SPIKE.exe"),
    ]
    return next((item for item in candidates if item and Path(item).exists()), None)


def launch_desktop(context: Dict[str, Any]) -> tuple[bool, str]:
    executable = find_desktop_executable()
    if not executable:
        return False, "SPIKE desktop is not installed or has not been built."
    context_path = write_context(context)
    try:
        subprocess.Popen([executable, "--context", str(context_path)],
                         cwd=str(Path(executable).parent),
                         creationflags=subprocess.DETACHED_PROCESS if sys.platform == "win32" else 0)
    except OSError as exc:
        return False, f"Could not launch SPIKE desktop: {exc}"
    return True, str(context_path)


if pcbnew is not None and wx is not None:
    class SPIKEPlugin(pcbnew.ActionPlugin):
        def defaults(self):
            self.name = "SPIKE - Power Integrity Workbench"
            self.category = "Analysis"
            self.description = "Open the standalone SPIKE PI/SI analysis workbench."
            self.show_toolbar_button = True
            icon = Path(__file__).parent / "spike_icon.png"
            if icon.exists():
                self.icon_file_name = str(icon)

        def Run(self):  # noqa: N802 - KiCad API method name
            board_path = ""
            try:
                board = pcbnew.GetBoard()
                if board:
                    board_path = board.GetFileName()
            except Exception as exc:
                wx.MessageBox(f"Could not read the active board: {exc}", "SPIKE")
                return
            ok, detail = launch_desktop(build_context(board_path))
            if not ok:
                wx.MessageBox(detail, "SPIKE desktop unavailable", wx.ICON_WARNING)

    SPIKEPlugin().register()
else:
    class SPIKEPlugin:
        """Placeholder for documentation tools and normal Python imports."""

        def defaults(self):
            return None

        def Run(self):  # noqa: N802
            raise RuntimeError("SPIKEPlugin.Run() requires KiCad's pcbnew environment")
