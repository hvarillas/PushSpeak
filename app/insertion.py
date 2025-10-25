import sys
import os
import shutil
import subprocess
import threading
import time
import random
import logging
from typing import Optional

import pyperclip
from pynput import keyboard


_kb = keyboard.Controller()


def insert_text_at_cursor(text: Optional[str], use_clipboard: bool = True) -> None:
    """Insert text into the application that currently has focus.
    Prefers clipboard paste (Cmd/Ctrl+V), falls back to simulated typing.
    """
    if not text:
        logging.warning("[INSERT] Texto vacío, no se insertará nada")
        return
    
    logging.debug(f"[INSERT] Insertando texto ({len(text)} caracteres)")
    logging.debug(f"[INSERT] use_clipboard={use_clipboard}")
    if use_clipboard:
        time.sleep(0.08)
        mod = keyboard.Key.cmd if sys.platform == "darwin" else keyboard.Key.ctrl
        pasted = False
        prev_clip = None
        ses = os.environ.get("XDG_SESSION_TYPE", "").lower()
        has_xdo = bool(shutil.which("xdotool"))
        has_wtype = bool(shutil.which("wtype"))
        logging.debug(f"[INSERT] Sesión: {ses}, xdotool: {has_xdo}, wtype: {has_wtype}")
        try:
            # Wayland with wtype: type directly, do not touch clipboard
            if ses == "wayland" and has_wtype:
                logging.debug("[INSERT] Intentando wtype (Wayland)")
                try:
                    rW = subprocess.run(["wtype", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                    pasted = (rW.returncode == 0)
                    if pasted:
                        logging.info("[INSERT] Texto insertado con wtype")
                    else:
                        logging.warning(f"[INSERT] wtype falló con código {rW.returncode}")
                except Exception as e:
                    logging.error(f"[INSERT] Error con wtype: {e}")
                    pasted = False
            if not pasted:
                try:
                    try:
                        prev_clip = pyperclip.paste()
                    except Exception:
                        prev_clip = None
                    pyperclip.copy(text)
                    time.sleep(0.05)
                    # X11 path: in terminals prefer Ctrl+Shift+V first (hotkey is disabled around paste), then Shift+Insert, then middle-click
                    if ses == "x11" and has_xdo:
                        is_terminal = _is_x11_terminal_window()
                        logging.debug(f"[INSERT] X11 detectado, es_terminal: {is_terminal}")
                        if is_terminal:
                            # terminals: try Ctrl+Shift+V, then Shift+Insert, then middle-click (PRIMARY)
                            logging.debug("[INSERT] Intentando Ctrl+Shift+V (terminal)")
                            try:
                                r_cs = subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+shift+v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.4)
                                pasted = (r_cs.returncode == 0)
                                if pasted:
                                    logging.info("[INSERT] Texto pegado con Ctrl+Shift+V")
                            except Exception as e:
                                logging.debug(f"[INSERT] Error con Ctrl+Shift+V: {e}")
                                pasted = False
                            if not pasted:
                                logging.debug("[INSERT] Intentando Shift+Insert (terminal)")
                                try:
                                    r2 = subprocess.run(["xdotool", "key", "--clearmodifiers", "Shift+Insert"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.4)
                                    pasted = (r2.returncode == 0)
                                    if pasted:
                                        logging.info("[INSERT] Texto pegado con Shift+Insert")
                                except Exception as e:
                                    logging.debug(f"[INSERT] Error con Shift+Insert: {e}")
                                    pasted = False
                            if not pasted:
                                logging.debug("[INSERT] Intentando clic medio/PRIMARY (terminal)")
                                try:
                                    _set_primary_selection(text)
                                    rc = subprocess.run(["xdotool", "click", "2"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.4)
                                    pasted = (rc.returncode == 0)
                                    if pasted:
                                        logging.info("[INSERT] Texto pegado con clic medio")
                                except Exception as e:
                                    logging.debug(f"[INSERT] Error con clic medio: {e}")
                                    pasted = False
                        else:
                            # non-terminals: prefer Ctrl+V
                            logging.debug("[INSERT] Intentando Ctrl+V (no-terminal)")
                            try:
                                r = subprocess.run(["xdotool", "key", "--clearmodifiers", "ctrl+v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.4)
                                pasted = (r.returncode == 0)
                                if pasted:
                                    logging.info("[INSERT] Texto pegado con Ctrl+V")
                            except Exception as e:
                                logging.debug(f"[INSERT] Error con Ctrl+V: {e}")
                                pasted = False
                    # Fallback to pynput paste
                    if not pasted:
                        logging.debug("[INSERT] Intentando pynput Ctrl+V")
                        try:
                            _kb.press(mod)
                            _kb.press(keyboard.KeyCode.from_char("v"))
                            _kb.release(keyboard.KeyCode.from_char("v"))
                            _kb.release(mod)
                            pasted = True
                            logging.info("[INSERT] Texto pegado con pynput")
                        except Exception as e:
                            logging.debug(f"[INSERT] Error con pynput: {e}")
                            pasted = False
                    # Try pynput: Ctrl+Shift+V in terminals, else Ctrl+V; as last resort Shift+Insert
                    if not pasted:
                        if ses == "x11" and _is_x11_terminal_window():
                            try:
                                _kb.press(mod)
                                _kb.press(keyboard.Key.shift)
                                _kb.press(keyboard.KeyCode.from_char("v"))
                                _kb.release(keyboard.KeyCode.from_char("v"))
                                _kb.release(keyboard.Key.shift)
                                _kb.release(mod)
                                pasted = True
                            except Exception:
                                pasted = False
                            if not pasted:
                                try:
                                    _kb.press(keyboard.Key.shift)
                                    _kb.press(keyboard.Key.insert)
                                    _kb.release(keyboard.Key.insert)
                                    _kb.release(keyboard.Key.shift)
                                    pasted = True
                                except Exception:
                                    pasted = False
                        else:
                            try:
                                _kb.press(mod)
                                _kb.press(keyboard.KeyCode.from_char("v"))
                                _kb.release(keyboard.KeyCode.from_char("v"))
                                _kb.release(mod)
                                pasted = True
                            except Exception:
                                pasted = False
                    # Alternative: Shift+Insert
                    if not pasted:
                        if ses == "x11" and has_xdo:
                            try:
                                r2 = subprocess.run(["xdotool", "key", "--clearmodifiers", "Shift+Insert"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.4)
                                pasted = (r2.returncode == 0)
                            except Exception:
                                pasted = False
                        if not pasted:
                            try:
                                _kb.press(keyboard.Key.shift)
                                _kb.press(keyboard.Key.insert)
                                _kb.release(keyboard.Key.insert)
                                _kb.release(keyboard.Key.shift)
                                pasted = True
                            except Exception:
                                pasted = False
                except Exception:
                    pasted = False
        finally:
            try:
                # Restore only if previous is non-empty and different
                if pasted and isinstance(prev_clip, str) and prev_clip.strip() and prev_clip != text:
                    threading.Timer(0.5, lambda: pyperclip.copy(prev_clip)).start()
            except Exception:
                pass

        if not pasted:
            logging.warning("[INSERT] Todos los métodos de pegado fallaron, usando tipeo")
            try:
                _kb.type(text)
                logging.info(f"[INSERT] Texto tipeado ({len(text)} caracteres)")
            except Exception as e:
                logging.error(f"[INSERT] Error tipeando texto: {e}")
    else:
        logging.debug("[INSERT] Modo tipeo directo (sin clipboard)")
        try:
            _kb.type(text)
            logging.info(f"[INSERT] Texto tipeado ({len(text)} caracteres)")
        except Exception as e:
            logging.error(f"[INSERT] Error tipeando texto: {e}")


def type_text(text: Optional[str]) -> None:
    """Type text directly without touching clipboard (for streaming)."""
    if not text:
        return
    try:
        _kb.type(text)
    except Exception:
        pass


def type_text_human(text: Optional[str], min_delay: float = 0.01, max_delay: float = 0.03) -> None:
    """Type text character by character with small random delays to mimic human speed."""
    if not text:
        return
    # small settle delay to let focus return
    time.sleep(0.05)
    try:
        for ch in text:
            _kb.type(ch)
            # avoid zero or negative delays
            d = max(0.0, random.uniform(min_delay, max_delay))
            time.sleep(d)
    except Exception:
        pass


def _is_x11_terminal_window() -> bool:
    try:
        if os.environ.get("XDG_SESSION_TYPE", "").lower() != "x11":
            return False
        if not shutil.which("xdotool") or not shutil.which("xprop"):
            return False
        wid = subprocess.run(["xdotool", "getactivewindow"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=0.2, text=True)
        win = wid.stdout.strip()
        if not win:
            return False
        pr = subprocess.run(["xprop", "-id", win, "WM_CLASS", "WM_NAME"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=0.4, text=True)
        s = pr.stdout.lower()
        terms = ["terminal", "gnome-terminal", "konsole", "alacritty", "xterm", "rxvt", "urxvt", "kitty", "tilix", "terminator", "rio"]
        return any(t in s for t in terms)
    except Exception:
        return False


def _set_primary_selection(text: str) -> None:
    try:
        if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland" and shutil.which("wl-copy"):
            subprocess.run(["wl-copy", "-p"], input=text.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
            return
        if shutil.which("xclip"):
            subprocess.run(["xclip", "-selection", "primary"], input=text.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
            return
        if shutil.which("xsel"):
            subprocess.run(["xsel", "-p", "-i"], input=text.encode("utf-8"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=0.5)
            return
    except Exception:
        pass
