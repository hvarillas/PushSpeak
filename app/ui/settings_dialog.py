from __future__ import annotations

import logging
from typing import Tuple

from qtpy import QtWidgets, QtGui, QtCore


def _combo_to_str(combo: set[str]) -> str:
    return "+".join(sorted(combo)) if combo else ""


def _str_to_combo(text: str) -> set[str]:
    toks = [t.strip().lower() for t in (text or "").replace(" ", "").split("+") if t.strip()]
    norm = []
    for t in toks:
        if t.startswith("ctrl"):
            norm.append("ctrl")
        elif t.startswith("shift"):
            norm.append("shift")
        elif t.startswith("alt"):
            norm.append("alt")
        elif t in ("cmd", "meta", "super", "win"):
            norm.append("cmd")
        else:
            norm.append(t)
    return set(norm)


class SettingsDialog(QtWidgets.QDialog):
    """Simple configuration dialog for shortcut, model path and language."""

    def __init__(self, parent=None, *,
                 combo: set[str] | None = None,
                 model_path: str = "",
                 language: str = "es",
                 hotkey_enabled: bool = True):
        # Evitar conflictos con pywebview: no pasar parent si causa problemas
        logging.debug("[SETTINGS] Inicializando diálogo de configuración")
        try:
            super().__init__(parent)
            logging.debug("[SETTINGS] Diálogo creado con parent")
        except (TypeError, RuntimeError) as e:
            logging.warning(f"[SETTINGS] Error con parent, usando None: {e}")
            super().__init__(None)
        
        self.setWindowTitle("Configuración")
        self.setModal(True)

        self._combo = set(combo or [])
        self._model_path = model_path
        self._language = language
        self._hotkey_enabled = bool(hotkey_enabled)

        form = QtWidgets.QFormLayout()

        # Hotkey enabled
        self.chk_enabled = QtWidgets.QCheckBox("Activar atajo (push‑to‑talk)")
        self.chk_enabled.setChecked(self._hotkey_enabled)
        form.addRow(self.chk_enabled)

        # Shortcut combo
        self.ed_combo = QtWidgets.QLineEdit(_combo_to_str(self._combo))
        self.ed_combo.setPlaceholderText("ctrl+shift")
        form.addRow("Atajo (p.ej. ctrl+shift)", self.ed_combo)

        # Model file chooser (manual entry due to pywebview conflicts)
        path_layout = QtWidgets.QHBoxLayout()
        self.ed_model = QtWidgets.QLineEdit(self._model_path)
        self.ed_model.setPlaceholderText("~/.models/ggml-small.bin")
        
        # Botón de ayuda en lugar de examinar (evita conflictos con pywebview)
        btn_help = QtWidgets.QPushButton("📁 Ayuda")
        btn_help.setToolTip("Ver instrucciones para ubicar el modelo")
        btn_help.clicked.connect(self._show_model_help)
        
        path_layout.addWidget(self.ed_model)
        path_layout.addWidget(btn_help)
        path_w = QtWidgets.QWidget()
        path_w.setLayout(path_layout)
        form.addRow("Modelo Whisper", path_w)

        # Language selector (editable combo)
        self.cb_lang = QtWidgets.QComboBox()
        self.cb_lang.setEditable(True)
        langs = ["auto", "es", "en", "fr", "de", "pt", "it"]
        self.cb_lang.addItems(langs)
        # If current language not in list, add it
        if self._language and self._language not in langs:
            self.cb_lang.addItem(self._language)
        self.cb_lang.setCurrentText(self._language or "es")
        form.addRow("Idioma", self.cb_lang)

        # Buttons
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _show_model_help(self):
        """Muestra ayuda para ubicar y descargar modelos"""
        logging.debug("[SETTINGS] Mostrando ayuda de modelos")
        import os
        
        # Verificar si existe el directorio de modelos
        models_dir = os.path.expanduser("~/.models")
        models_exist = os.path.exists(models_dir)
        
        # Listar modelos disponibles si el directorio existe
        available_models = []
        if models_exist:
            try:
                files = [f for f in os.listdir(models_dir) if f.endswith(('.bin', '.gguf'))]
                available_models = files[:5]  # Máximo 5
            except Exception:
                pass
        
        # Construir mensaje
        msg = "📁 <b>Ubicación del Modelo de Whisper</b><br><br>"
        
        if available_models:
            msg += "✅ <b>Modelos encontrados en ~/.models:</b><br>"
            for model in available_models:
                full_path = os.path.join(models_dir, model)
                msg += f"  • <code>~/.models/{model}</code><br>"
            msg += "<br>💡 <b>Tip:</b> Copia la ruta completa y pégala en el campo de texto.<br><br>"
        else:
            msg += "⚠️ <b>No se encontraron modelos en ~/.models</b><br><br>"
        
        msg += "<b>Para descargar un modelo:</b><br>"
        msg += "1. Abre una terminal<br>"
        msg += "2. Ejecuta:<br>"
        msg += "<code>cd /mnt/d/develop/own/python/PushSpeak</code><br>"
        msg += "<code>./scripts/download_model.sh</code><br><br>"
        
        msg += "<b>O descarga manualmente:</b><br>"
        msg += "<code>mkdir -p ~/.models</code><br>"
        msg += "<code>cd ~/.models</code><br>"
        msg += "<code>wget https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin</code><br><br>"
        
        msg += "<b>Luego ingresa la ruta:</b><br>"
        msg += "<code>~/.models/ggml-small.bin</code>"
        
        msgbox = QtWidgets.QMessageBox(self)
        msgbox.setWindowTitle("Ayuda: Modelo de Whisper")
        msgbox.setTextFormat(QtCore.Qt.RichText)
        msgbox.setText(msg)
        msgbox.setIcon(QtWidgets.QMessageBox.Information)
        msgbox.exec_()

    def values(self) -> Tuple[set[str], str, str, bool]:
        combo = _str_to_combo(self.ed_combo.text())
        model = self.ed_model.text().strip()
        lang = (self.cb_lang.currentText() or "es").strip()
        enabled = self.chk_enabled.isChecked()
        logging.debug(f"[SETTINGS] Valores: combo={combo}, model={model}, lang={lang}, enabled={enabled}")
        return combo, model, lang, enabled

    # Provide Qt5-style exec_ for compatibility
    def exec_(self) -> int:  # type: ignore[override]
        return super().exec()
