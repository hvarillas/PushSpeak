import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from pynput import keyboard

from app.config import (
    AudioConfig,
    WhisperConfig,
    UIConfig,
    COMBO_RECORD,
    INSERT_TRAILING,
)
from app.state import AppState
from app.audio.recorder import Recorder, RecorderConfig
from app.audio.monitor import LiveMonitor
from app.ui.window import UIWindow
from app.transcribe import verify_whisper, transcribe_audio
from app.insertion import insert_text_at_cursor, type_text_human
from app.focus import get_active_window, activate_window
import logging


"""
Simplified non-real-time mode: push-to-talk recording with ffmpeg, then full-file transcription via whisper-cli.
All real-time streaming, UI and monitoring dependencies removed from runtime.
"""


def _verificar_ffmpeg() -> bool:
    try:
        res = subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3,
        )
        return res.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _detectar_sistema_audio(cfg: AudioConfig) -> AudioConfig:
    try:
        res = subprocess.run(
            ["pactl", "info"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2
        )
        if res.returncode == 0:
            return AudioConfig(
                sample_rate=cfg.sample_rate,
                channels=cfg.channels,
                codec=cfg.codec,
                output_format=cfg.output_format,
                input_device="default",
                device_system="pulse",
            )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return AudioConfig(
        sample_rate=cfg.sample_rate,
        channels=cfg.channels,
        codec=cfg.codec,
        output_format=cfg.output_format,
        input_device="default",
        device_system="alsa",
    )


class HotkeyListener:
    def __init__(
        self, on_start, on_stop, *, combo: set[str] | None = None, enabled: bool = True
    ):
        self.on_start = on_start
        self.on_stop = on_stop
        self._pressed: set[str] = set()
        self._listener: keyboard.Listener | None = None
        self._active = False
        self._watchdog: threading.Thread | None = None
        self._stop_watch = threading.Event()
        self._combo: set[str] = set(combo or set(COMBO_RECORD))
        self._enabled: bool = bool(enabled)

    def _on_press(self, key):
        if not self._enabled:
            return
        name = getattr(key, "char", None)
        if name:
            name = name.lower()
        else:
            name = getattr(key, "name", str(key)).lower()
        # normalize left/right variants
        if name and name.startswith("ctrl"):
            name = "ctrl"
        if name and name.startswith("shift"):
            name = "shift"
        if name and name.startswith("alt"):
            name = "alt"
        if name in self._combo and len(self._pressed) < len(self._combo):
            self._pressed.add(name)
            if not self._active and self._pressed == set(self._combo):
                self._active = True
                self.on_start()

    def _on_release(self, key):
        if key == keyboard.Key.esc:
            # handled by main via SIGINT
            return False
        if not self._enabled:
            return
        name = getattr(key, "char", None)
        if name:
            name = name.lower()
        else:
            name = getattr(key, "name", str(key)).lower()
        # normalize left/right variants
        if name and name.startswith("ctrl"):
            name = "ctrl"
        if name and name.startswith("shift"):
            name = "shift"
        if name and name.startswith("alt"):
            name = "alt"
        if name in self._pressed:
            self._pressed.discard(name)
        if self._active and self._pressed != set(self._combo):
            self._active = False
            self.on_stop()

    def _ensure_listener(self):
        # Create (or recreate) listener if not running
        try:
            if self._listener and getattr(self._listener, "is_alive", lambda: False)():
                return
        except Exception:
            pass
        try:
            self._listener = keyboard.Listener(
                on_press=self._on_press, on_release=self._on_release
            )
            self._listener.daemon = True
            self._listener.start()
        except Exception:
            self._listener = None

    def _watch(self):
        while not self._stop_watch.is_set():
            try:
                self._ensure_listener()
            except Exception:
                pass
            # clean stuck state if any
            if self._active and not self._pressed:
                self._active = False
            self._stop_watch.wait(1.0)

    def start(self):
        self._stop_watch.clear()
        self._ensure_listener()
        if not self._watchdog or not self._watchdog.is_alive():
            self._watchdog = threading.Thread(target=self._watch, daemon=True)
            self._watchdog.start()

    def stop(self):
        self._stop_watch.set()
        try:
            if self._watchdog:
                self._watchdog.join(timeout=1)
        except Exception:
            pass
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
            finally:
                self._listener = None

    # dynamic controls
    def set_combo(self, combo: set[str]):
        try:
            self._combo = set(combo or [])
        except Exception:
            pass

    def set_enabled(self, enabled: bool):
        self._enabled = bool(enabled)

    def get_combo(self) -> set[str]:
        return set(self._combo)

    def is_enabled(self) -> bool:
        return bool(self._enabled)


def main() -> int:
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    if not _verificar_ffmpeg():
        logging.error("ffmpeg no esta instalado")
        return 1

    audio_cfg = _detectar_sistema_audio(AudioConfig())
    whisper_cfg = WhisperConfig()
    ui_cfg = UIConfig()

    # Validate CLI availability (non-RT mode)
    if whisper_cfg.auto_transcribe:
        if not verify_whisper():
            logging.warning(
                "whisper-cli no esta disponible. Transcripcion deshabilitada."
            )
            whisper_cfg = WhisperConfig(
                model_path=whisper_cfg.model_path,
                language=whisper_cfg.language,
                auto_transcribe=False,
            )

    state = AppState(recording=False, audio_buffer=[], current_file=None)

    # UI window (wavebar)
    template = Path(__file__).resolve().parents[1] / "templates" / "wavebar.html"
    win = UIWindow(
        width=ui_cfg.width,
        height=ui_cfg.height,
        template_path=template,
        get_state=lambda: {
            "grabando": state.recording,
            "data": state.audio_buffer or [],
            "text": state.rt_text,
        },
    )
    window = win.create()
    state.window = window

    # Preload streaming model once if using streaming backend (cached)
    try:
        if whisper_cfg.rt_backend == "whisper_stream":
            from app.transcribe import ensure_fw_model_preloaded

            ensure_fw_model_preloaded(
                whisper_cfg.stream_model,
                whisper_cfg.stream_device,
                whisper_cfg.stream_compute_type,
            )
    except Exception:
        pass

    # Recorder and live monitor (visuals only)
    recorder = Recorder(
        RecorderConfig(
            device_system=audio_cfg.device_system,
            input_device=audio_cfg.input_device,
            sample_rate=audio_cfg.sample_rate,
            channels=audio_cfg.channels,
            codec=audio_cfg.codec,
            output_format=audio_cfg.output_format,
        )
    )
    monitor = LiveMonitor(
        audio_cfg.sample_rate,
        on_data=lambda buf: setattr(state, "audio_buffer", buf),
        on_raw=None,
    )

    def start_recording():
        if state.recording:
            logging.debug("[MAIN] start_recording() llamado pero ya está grabando")
            return
        logging.info("[MAIN] === INICIANDO GRABACIÓN ===")
        try:
            # Capture current focused window (X11) before showing UI
            state.active_window_id = get_active_window()
            logging.debug(f"[MAIN] Ventana activa capturada: {state.active_window_id}")
            
            state.current_file = recorder.start()
            logging.debug(f"[MAIN] Archivo de grabación: {state.current_file}")
            
            state.recording = True
            state.rt_text = ""
            state.rt_committed = ""
            
            monitor.start()
            logging.debug("[MAIN] Monitor de audio iniciado")
            
            win.bottom_center(margin_bottom=ui_cfg.bottom_margin)
            win.show_with_fade()
            logging.debug("[MAIN] UI mostrada")
            
            # Try to restore focus to previously active window (best-effort)
            if state.active_window_id:
                threading.Timer(
                    0.03, lambda: activate_window(state.active_window_id)
                ).start()
                threading.Timer(
                    0.15, lambda: activate_window(state.active_window_id)
                ).start()
            logging.info("[MAIN] Grabación activa. Suelta el atajo para detener.")
        except Exception as e:
            logging.error(f"[MAIN] Error al iniciar la grabación: {e}", exc_info=True)
            state.recording = False

    def stop_recording():
        if not state.recording:
            logging.debug("[MAIN] stop_recording() llamado pero no está grabando")
            return
        logging.info("[MAIN] === DETENIENDO GRABACIÓN ===")
        try:
            monitor.stop()
            logging.debug("[MAIN] Monitor de audio detenido")
            
            saved = recorder.stop()
            state.recording = False
            
            win.hide_with_fade()
            logging.debug("[MAIN] UI ocultada")
            
            if not saved:
                logging.error("[MAIN] No se guardó archivo de audio")
                return
            
            logging.info(f"[MAIN] Archivo guardado: {saved}")
            
            final_text = None
            if whisper_cfg.auto_transcribe:
                logging.info("[MAIN] Iniciando transcripción...")
                final_text = transcribe_audio(
                    saved, settings["model_path"], settings["language"]
                )
                
                # Eliminar archivo temporal después de la transcripción
                try:
                    if os.path.exists(saved):
                        os.remove(saved)
                        logging.debug(f"[MAIN] Archivo temporal eliminado: {saved}")
                except Exception as e:
                    logging.warning(f"[MAIN] No se pudo eliminar archivo temporal: {e}")
            else:
                logging.info("[MAIN] Transcripción deshabilitada en config")

            if final_text:
                logging.info(f"[MAIN] Texto transcrito: '{final_text[:50]}...' ({len(final_text)} chars)")
                acc_text = final_text + INSERT_TRAILING
                
                if state.active_window_id:
                    logging.debug(f"[MAIN] Restaurando foco a ventana: {state.active_window_id}")
                    threading.Timer(
                        0.10, lambda: activate_window(state.active_window_id)
                    ).start()
                    threading.Timer(
                        0.35, lambda: activate_window(state.active_window_id)
                    ).start()

                def _do_insert():
                    logging.debug("[MAIN] Ejecutando inserción de texto")
                    prev_enabled = False
                    try:
                        prev_enabled = hotkeys.is_enabled()
                        # Temporarily disable hotkey to avoid Ctrl+Shift paste re-triggering recording
                        hotkeys.set_enabled(False)
                        logging.debug(f"[MAIN] Atajo deshabilitado temporalmente (prev: {prev_enabled})")
                    except Exception as e:
                        logging.warning(f"[MAIN] Error deshabilitando atajo: {e}")
                    try:
                        insert_text_at_cursor(acc_text, use_clipboard=True)
                    finally:
                        try:
                            # Restore to previous state after a short delay
                            threading.Timer(
                                0.4, lambda: hotkeys.set_enabled(prev_enabled)
                            ).start()
                            logging.debug(f"[MAIN] Atajo será restaurado a: {prev_enabled}")
                        except Exception as e:
                            logging.warning(f"[MAIN] Error restaurando atajo: {e}")

                threading.Timer(0.80, _do_insert).start()
            else:
                logging.warning("[MAIN] No se obtuvo texto de la transcripción")
        except Exception as e:
            logging.error(f"[MAIN] Error al detener la grabación: {e}", exc_info=True)
            state.recording = False

    # Runtime settings
    settings = {
        "combo": set(COMBO_RECORD),
        "hotkey_enabled": False,  # dictáfono desactivado por defecto
        "model_path": whisper_cfg.model_path,
        "language": whisper_cfg.language,
    }

    # Resolve model path: expand ~ and make absolute if needed
    try:
        root = Path(__file__).resolve().parents[1]
        if settings["model_path"]:
            # Expand ~ first
            model_path = Path(settings["model_path"]).expanduser()
            # If still not absolute, make it relative to project root
            if not model_path.is_absolute():
                model_path = (root / model_path).resolve()
            settings["model_path"] = str(model_path)
    except Exception:
        pass

    hotkeys = HotkeyListener(
        on_start=start_recording,
        on_stop=stop_recording,
        combo=settings["combo"],
        enabled=settings["hotkey_enabled"],
    )

    def handle_sig(sig, frame):
        try:
            hotkeys.stop()
            try:
                monitor.stop()
            except Exception:
                pass
            try:
                recorder.stop()
            except Exception:
                pass
            try:
                import webview

                for w in list(webview.windows):
                    try:
                        w.destroy()
                    except Exception:
                        pass
            except Exception:
                pass
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, handle_sig)
    try:
        signal.signal(signal.SIGTERM, handle_sig)
    except Exception:
        pass

    logging.info("*** Dictafono ***")
    logging.info(
        f"[AUDIO] Sistema: {audio_cfg.device_system} / Dispositivo: {audio_cfg.input_device}"
    )
    if whisper_cfg.auto_transcribe:
        logging.info("[AI] Transcripcion al soltar: Activada")
    logging.info("Mantén Ctrl+Shift para grabar. Esc para salir.")

    hotkeys.start()

    import webview

    # Tray init: schedule creation on Qt main thread (pywebview runs func in worker thread)
    def _init_tray():
        try:
            from qtpy import QtWidgets, QtGui, QtCore
            from app.ui.settings_dialog import SettingsDialog

            app = QtWidgets.QApplication.instance()
            if app is None:
                return
            try:
                app.setQuitOnLastWindowClosed(False)
            except Exception:
                pass

            if not QtWidgets.QSystemTrayIcon.isSystemTrayAvailable():
                return

            class _TrayBuilder(QtCore.QObject):
                def __init__(self, parent=None):
                    super().__init__(parent)

                @QtCore.Slot()
                def build(self):
                    icon = QtGui.QIcon.fromTheme("audio-input-microphone")
                    if icon.isNull():
                        pm = QtGui.QPixmap(16, 16)
                        pm.fill(QtGui.QColor("#555"))
                        icon = QtGui.QIcon(pm)
                    tray = QtWidgets.QSystemTrayIcon(icon, app)
                    tray.setToolTip("Dictáfono")

                    menu = QtWidgets.QMenu()

                    # Toggle enable/disable hotkey binding
                    act_toggle = menu.addAction("Activar atajo (push‑to‑talk)")
                    act_toggle.setCheckable(True)
                    try:
                        act_toggle.setChecked(hotkeys.is_enabled())
                    except Exception:
                        act_toggle.setChecked(False)

                    def on_toggle(checked: bool):
                        settings["hotkey_enabled"] = bool(checked)
                        hotkeys.set_enabled(bool(checked))

                    act_toggle.toggled.connect(on_toggle)

                    def open_settings():
                        dlg = SettingsDialog(
                            None,
                            combo=hotkeys.get_combo(),
                            model_path=settings["model_path"],
                            language=settings["language"],
                            hotkey_enabled=hotkeys.is_enabled(),
                        )
                        res = dlg.exec_()
                        if res == QtWidgets.QDialog.Accepted:
                            combo, model, lang, enabled = dlg.values()
                            if combo:
                                settings["combo"] = set(combo)
                                hotkeys.set_combo(settings["combo"])
                            if model and model != settings["model_path"]:
                                try:
                                    # Expand ~ first
                                    model_path = Path(model).expanduser()
                                    # If still not absolute, make it relative to project root
                                    if not model_path.is_absolute():
                                        model_path = (root / model_path).resolve()
                                    model = str(model_path)
                                except Exception:
                                    pass
                                settings["model_path"] = model
                                # No-op for CLI; if streaming backend active, ensure cached model if applicable
                                try:
                                    if whisper_cfg.rt_backend == "whisper_stream":
                                        from app.transcribe import (
                                            ensure_fw_model_preloaded,
                                        )

                                        ensure_fw_model_preloaded(
                                            whisper_cfg.stream_model,
                                            whisper_cfg.stream_device,
                                            whisper_cfg.stream_compute_type,
                                        )
                                except Exception:
                                    pass
                            if lang:
                                settings["language"] = lang
                            hotkeys.set_enabled(enabled)
                            try:
                                act_toggle.setChecked(enabled)
                            except Exception:
                                pass

                    act_conf = menu.addAction("Configuración…")
                    act_conf.triggered.connect(open_settings)

                    menu.addSeparator()

                    def do_quit():
                        handle_sig(None, None)

                    act_quit = menu.addAction("Salir")
                    act_quit.triggered.connect(do_quit)

                    tray.setContextMenu(menu)
                    tray.show()
                    # Keep references on QApplication to prevent GC
                    app._tray_ref = tray  # type: ignore[attr-defined]
                    app._tray_menu = menu  # type: ignore[attr-defined]

            builder = _TrayBuilder()
            # Execute in the main Qt thread
            builder.moveToThread(app.thread())
            QtCore.QMetaObject.invokeMethod(
                builder, "build", QtCore.Qt.QueuedConnection
            )
            app._tray_builder = builder  # type: ignore[attr-defined]
        except Exception:
            pass

    try:
        webview.start(func=_init_tray)
    except KeyboardInterrupt:
        handle_sig(None, None)
    return 0
