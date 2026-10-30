"""Qt side of i18n: switching the language while the app runs, Qt's own strings, and locale-aware formatting.

* ``apply_language(setting)``: the one entry point ('auto', 'en' or 'es'). It sets the ``core.i18n`` language, swaps
  the ``QTranslator`` that translates Qt's built-in texts (standard buttons, context menus, file dialogs), re-applies
  every ``bind_text`` binding and emits ``language_bus().changed`` so windows can refresh what they built by hand.
* ``bind_text(widget, "setText", "Get info")``: set a widget's text now and again on every language change, so the
  widget never has to be touched by a ``refresh_language`` method.
* ``format_number`` / ``format_date`` / ``format_datetime``: numbers and dates the way the active language writes them.
"""

from __future__ import annotations

import datetime as _dt
import weakref
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QCoreApplication, QDate, QLibraryInfo, QLocale, QObject, QTime, QTranslator, Signal

from core import i18n
from core.i18n import LANG_AUTO, LANG_EN, SUPPORTED_LANGUAGES, resolve_language, t

QT_CATALOGS = ("qtbase",)  # Qt's own translations that matter for this app (buttons, menus, dialogs)


class _LanguageBus(QObject):
    changed = Signal(str)  # the resolved language code ('en' / 'es')


_bus: _LanguageBus | None = None
_setting = LANG_AUTO
_qt_translators: list[QTranslator] = []
_bindings: dict[tuple[int, str], tuple[Any, Any, Callable[[], str]]] = {}


def language_bus() -> _LanguageBus:
    global _bus
    if _bus is None:
        _bus = _LanguageBus()
    return _bus


# ----------------------------------------------------------------------------------------------------------------- #
# Detection and switching
# ----------------------------------------------------------------------------------------------------------------- #


def language_from_names(names: list[str]) -> str:
    """First supported language in a list of locale names (``["pt-BR", "es-UY"]`` gives ``"es"``), else English."""
    for name in names:
        base = name.replace("_", "-").split("-")[0].split(".")[0].lower()
        if base in SUPPORTED_LANGUAGES:
            return base
    return LANG_EN


def system_language() -> str:
    """The language of the operating system as a supported code, from ``QLocale`` (reliable on Windows and macOS)."""
    loc = QLocale.system()
    return language_from_names(list(loc.uiLanguages()) + [loc.name()])


def current_setting() -> str:
    """What the user chose: 'auto', 'en' or 'es' (not the resolved language)."""
    return _setting


def language_choices() -> list[tuple[str, str]]:
    """(setting, label) for a language picker: Auto first, then each language under its own name."""
    return [(LANG_AUTO, t("Auto (system)"))] + [(code, name) for code, name in SUPPORTED_LANGUAGES.items()]


def _qt_translations_dirs() -> list[str]:
    return [str(i18n.LOCALE_DIR / "qt"), QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)]


def load_qt_translator(name: str, lang: str) -> QTranslator | None:
    """Load Qt's own catalog (``qtbase_es.qm``) from our ``locale/qt`` folder, else from the PySide6 install."""
    translator = QTranslator()
    for directory in _qt_translations_dirs():
        if translator.load(f"{name}_{lang}", directory):
            return translator
    return None


def install_qt_translators(lang: str) -> bool:
    """Replace the installed Qt translators with the ones of ``lang``; True when Qt's own texts are translated."""
    app = QCoreApplication.instance()
    for tr in _qt_translators:
        if app is not None:
            QCoreApplication.removeTranslator(tr)
    _qt_translators.clear()
    if lang == LANG_EN:
        return True
    ok = True
    for name in QT_CATALOGS:
        translator = load_qt_translator(name, lang)
        if translator is None:
            ok = False
        elif app is not None:
            QCoreApplication.installTranslator(translator)
            _qt_translators.append(translator)
    return ok


def apply_language(setting: str, *, announce: bool = True) -> str:
    """Switch the whole interface to ``setting`` ('auto', 'en', 'es'); returns the resolved language code."""
    global _setting
    _setting = setting if setting in (LANG_AUTO, *SUPPORTED_LANGUAGES) else LANG_AUTO
    resolved = resolve_language(_setting, system_language())
    i18n.set_language(resolved)
    install_qt_translators(resolved)
    retranslate_bindings()
    if announce:
        language_bus().changed.emit(resolved)
    return resolved


# ----------------------------------------------------------------------------------------------------------------- #
# Bindings
# ----------------------------------------------------------------------------------------------------------------- #


def bind(widget: Any, setter: str | Callable[[Any, str], None], factory: Callable[[], str]) -> None:
    """Call ``setter`` with ``factory()`` now and after every language change (the widget is held weakly).

    ``setter`` is a method name (``"setText"``) or a function ``(widget, text)``. Binding the same widget and setter
    again replaces the old binding. ``factory`` is called each time, so it may build text from live values.
    """
    key = (id(widget), setter if isinstance(setter, str) else getattr(setter, "__qualname__", repr(setter)))
    _bindings[key] = (weakref.ref(widget), setter, factory)
    _apply(widget, setter, factory)


def bind_text(widget: Any, setter: str, text: str, **params: Any) -> None:
    """``bind`` for a plain message: ``bind_text(button, "setText", "Get info")``, placeholders as keywords."""
    bind(widget, setter, lambda: t(text, **params))


def _apply(widget: Any, setter: str | Callable[[Any, str], None], factory: Callable[[], str]) -> bool:
    try:
        value = factory()
        if isinstance(setter, str):
            getattr(widget, setter)(value)
        else:
            setter(widget, value)
        return True
    except RuntimeError:  # the C++ widget is already deleted
        return False


def retranslate_bindings() -> None:
    for key, (ref, setter, factory) in list(_bindings.items()):
        widget = ref()
        if widget is None or not _apply(widget, setter, factory):
            _bindings.pop(key, None)


# ----------------------------------------------------------------------------------------------------------------- #
# Locale-aware formatting
# ----------------------------------------------------------------------------------------------------------------- #


def active_locale() -> QLocale:
    """``QLocale`` of the language being shown (not of the OS: an English UI on a Spanish PC prints ``1.5``)."""
    return QLocale(i18n.get_language())


def format_number(value: float, decimals: int = 0) -> str:
    """``1.5`` in English, ``1,5`` in Spanish (no thousands separators: the UI is compact)."""
    loc = active_locale()
    loc.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    return loc.toString(float(value), "f", decimals)


def format_date(value: _dt.date | str, *, long: bool = False) -> str:
    """Short (``30/10/26``) or long (``viernes, 30 de octubre de 2026``) date in the active language."""
    if isinstance(value, str):
        try:
            value = _dt.date.fromisoformat(value[:10])
        except Exception:
            return value
    fmt = QLocale.FormatType.LongFormat if long else QLocale.FormatType.ShortFormat
    return active_locale().toString(QDate(value.year, value.month, value.day), fmt)


def format_datetime(value: _dt.datetime | str) -> str:
    """Short date and time in the active language (seconds and time zone are left out)."""
    if isinstance(value, str):
        try:
            value = _dt.datetime.fromisoformat(value)
        except Exception:
            return value
    loc = active_locale()
    qdate = QDate(value.year, value.month, value.day)
    return f"{loc.toString(qdate, QLocale.FormatType.ShortFormat)} {loc.toString(QTime(value.hour, value.minute), QLocale.FormatType.ShortFormat)}"
