from __future__ import annotations

import pathlib
import webview
from typing import Callable


class AppAPI:
    def __init__(self, get_state: Callable[[], dict]):
        self._get_state = get_state

    def get_state(self) -> dict:
        return self._get_state()

    def close(self) -> None:
        try:
            webview.windows[0].destroy()
        except Exception:
            pass


class UIWindow:
    def __init__(self, width: int, height: int, template_path: pathlib.Path, get_state: Callable[[], dict]):
        self.width = width
        self.height = height
        self.template_path = template_path
        self._api = AppAPI(get_state)
        self.window = None

    def create(self):
        html = self.template_path.read_text(encoding="utf-8")
        self.window = webview.create_window(
            "Audio Recorder",
            html=html,
            width=self.width,
            height=self.height,
            on_top=True,
            frameless=True,
            easy_drag=True,
            transparent=True,
            hidden=True,
            js_api=self._api,
        )
        return self.window

    def bottom_center(self, margin_bottom: int = 60):
        try:
            scr = webview.screens[0]
            sw, sh = int(scr.width), int(scr.height)
            x = max(0, int((sw - self.width) / 2))
            y = max(0, int(sh - self.height - margin_bottom))
            self.window.move(x, y)
        except Exception:
            pass

    def show_with_fade(self):
        try:
            self.window.show()
            self.window.evaluate_js("fadeIn()")
            # Try to avoid stealing focus from the target app
            self.window.evaluate_js("try{window.blur();document.activeElement&&document.activeElement.blur()}catch(e){}")
        except Exception:
            pass

    def hide_with_fade(self):
        try:
            self.window.evaluate_js("fadeOut()")
        except Exception:
            pass
        try:
            import threading

            threading.Timer(0.55, lambda: self.window.hide()).start()
        except Exception:
            pass
