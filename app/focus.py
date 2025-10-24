import os
import shutil
import subprocess
from typing import Optional


def _is_x11() -> bool:
    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "x11":
        return True
    if os.environ.get("WAYLAND_DISPLAY"):
        return False
    # default assume X11 if unknown
    return True


def get_active_window() -> Optional[str]:
    if not _is_x11():
        return None
    if not shutil.which("xdotool"):
        return None
    try:
        res = subprocess.run(["xdotool", "getactivewindow"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=0.2, text=True)
        win_id = res.stdout.strip()
        return win_id or None
    except Exception:
        return None


def activate_window(win_id: Optional[str]) -> bool:
    if not win_id:
        return False
    if not _is_x11() or not shutil.which("xdotool"):
        return False
    try:
        subprocess.run(["xdotool", "windowactivate", "--sync", win_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.3)
        return True
    except Exception:
        return False
