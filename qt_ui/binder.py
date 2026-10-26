"""SettingsBinder: connects the controls of the Options tab to the keys of the settings dictionary (decision D3).

It replaces the tkinter ``App.var()`` variables. The dictionary is the one ``MainWindow`` owns (and saves when the
window closes); the binder only edits it. Rules:

  * Loading a value into a control never writes it back, so a saved value that the control cannot show (a number in
    a field that only takes whole numbers, a word that is not in a drop-down) stays in the dictionary until the
    person changes that control.
  * An on/off control writes a real ``bool``; every other control writes a ``str`` (numbers are strings in the
    settings file, as the tkinter app saved them).
  * ``changed(key)`` fires after every change made by the person AND by ``set()``, so the tab can refresh its
    examples and the window can tell the Plan tab (Phase 6) that a setting it reads has changed.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QAbstractButton, QComboBox, QLineEdit, QSpinBox, QWidget

from core.settings import DEFAULTS


class SettingsBinder(QObject):
    changed = Signal(str)

    def __init__(self, settings: dict, parent: QObject | None = None):
        super().__init__(parent)
        self.settings = settings
        self.controls: dict[str, QWidget] = {}
        self._keys: dict[QWidget, str] = {}
        self._loading = 0

    # ---------------------------------------------------------------- binding
    # The slots are methods (no lambdas that capture ``self``): a lambda would put a reference cycle between the
    # binder and the controls, and the garbage collector breaks such cycles at the wrong moment (see HANDOFF.md).
    def bind(self, key: str, control: QWidget) -> QWidget:
        """Show the setting ``key`` in ``control`` and write the person's edits back. Returns the control."""
        if key not in DEFAULTS:
            raise KeyError(f"not a setting: {key}")
        if key in self.controls:
            raise ValueError(f"{key} is already bound")
        if isinstance(control, QAbstractButton):  # Toggle
            control.toggled.connect(self._on_toggled)
        elif isinstance(control, QLineEdit):
            control.textChanged.connect(self._on_text)
        elif isinstance(control, QComboBox):
            control.currentIndexChanged.connect(self._on_index)
        elif isinstance(control, QSpinBox):
            control.valueChanged.connect(self._on_value)
        else:
            raise TypeError(f"cannot bind a {type(control).__name__}")
        self.controls[key] = control
        self._keys[control] = key
        self._load(key, control)
        return control

    def _on_toggled(self, on: bool) -> None:
        self._edited(self.sender(), bool(on))

    def _on_text(self, text: str) -> None:
        self._edited(self.sender(), text)

    def _on_index(self, index: int) -> None:
        box = self.sender()
        if isinstance(box, QComboBox) and index >= 0:  # -1 = «nothing chosen» (a saved word that is not in the list)
            self._edited(box, box.itemText(index))

    def _on_value(self, value: int) -> None:
        self._edited(self.sender(), str(value))

    def _edited(self, control, value) -> None:
        key = self._keys.get(control)
        if key is None or self._loading:
            return
        self.settings[key] = value
        self.changed.emit(key)

    def _load(self, key: str, control: QWidget) -> None:
        value = self.settings.get(key, DEFAULTS[key])
        self._loading += 1  # not blockSignals: a Toggle needs its own ``toggled`` to slide the knob
        try:
            if isinstance(control, QAbstractButton):
                control.setChecked(_as_bool(value))
            elif isinstance(control, QLineEdit):
                control.setText(value if isinstance(value, str) else str(value))
            elif isinstance(control, QComboBox):
                control.setCurrentIndex(control.findText(value if isinstance(value, str) else str(value)))
            elif isinstance(control, QSpinBox):
                try:
                    control.setValue(int(float(value)))
                except (ValueError, TypeError, OverflowError):
                    control.setValue(control.minimum())
        finally:
            self._loading -= 1

    # ---------------------------------------------------------------- from code
    def set(self, key: str, value) -> None:
        """Change a setting from code: the control follows and ``changed`` fires (like ``StringVar.set``)."""
        self.settings[key] = value
        control = self.controls.get(key)
        if control is not None:
            self._load(key, control)
        self.changed.emit(key)

    def get(self, key: str):
        return self.settings.get(key, DEFAULTS[key])

    def reload(self) -> None:
        """Show the dictionary's values in every control again (nothing is written)."""
        for key, control in self.controls.items():
            self._load(key, control)


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "t", "y"}
    return bool(value)
