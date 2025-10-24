from __future__ import annotations

from typing import Tuple

from qtpy import QtWidgets, QtGui


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
        super().__init__(parent)
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

        # Model file chooser
        path_layout = QtWidgets.QHBoxLayout()
        self.ed_model = QtWidgets.QLineEdit(self._model_path)
        btn_browse = QtWidgets.QPushButton("Examinar…")
        btn_browse.clicked.connect(self._browse_model)
        path_layout.addWidget(self.ed_model)
        path_layout.addWidget(btn_browse)
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

    def _browse_model(self):
        dlg = QtWidgets.QFileDialog(self, "Seleccionar modelo de Whisper")
        dlg.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        # QtPy compatibility: exec_ on Qt5, exec on Qt6
        ok = dlg.exec_() if hasattr(dlg, "exec_") else dlg.exec()
        if ok:
            files = dlg.selectedFiles()
            if files:
                self.ed_model.setText(files[0])

    def values(self) -> Tuple[set[str], str, str, bool]:
        combo = _str_to_combo(self.ed_combo.text())
        model = self.ed_model.text().strip()
        lang = (self.cb_lang.currentText() or "es").strip()
        enabled = self.chk_enabled.isChecked()
        return combo, model, lang, enabled

    # Provide Qt5-style exec_ for compatibility
    def exec_(self) -> int:  # type: ignore[override]
        return super().exec()
