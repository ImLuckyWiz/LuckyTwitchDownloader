"""Tests for the Qt side of i18n (Phase I1): detection, Qt's own translations, bindings, formatting, packaging."""

from __future__ import annotations

import datetime as dt
import gc
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QDialogButtonBox, QLabel, QPushButton

from core import i18n
from core.i18n import (
    LANG_AUTO,
    LANG_EN,
    LANG_ES,
    get_system_language,
    language_from_locale_name,
    resolve_language,
)
from qt_ui import i18n_qt

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _english_after_each_test():
    yield
    i18n.set_locale_dir(ROOT / "locale")
    i18n_qt.apply_language(LANG_EN, announce=False)


# ----------------------------------------------------------------------------------------------------------------- #
# Detection (no hard-coded locale guess, no deprecated getdefaultlocale)
# ----------------------------------------------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "name, expected",
    [
        ("es", "es"), ("es_UY", "es"), ("es_UY.UTF-8", "es"), ("es-ES", "es"), ("ES_ar", "es"), ("es_MX@euro", "es"),
        ("Spanish_Uruguay", "es"), ("Spanish_Spain.1252", "es"),
        ("en", "en"), ("en_US", "en"), ("en-GB", "en"),
        ("pt_BR", "en"), ("fr_FR", "en"), ("C", "en"), ("POSIX", "en"), ("", "en"), (None, "en"),
        ("esperanto", "en"),  # starts with "es" but is not Spanish
    ],
)
def test_language_from_locale_name(name, expected):
    assert language_from_locale_name(name) == expected


def test_get_system_language_environment_order(monkeypatch):
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    monkeypatch.setenv("LC_ALL", "es_ES.UTF-8")
    assert get_system_language() == LANG_ES  # LC_ALL wins, like gettext
    monkeypatch.setenv("LC_ALL", "C")
    assert get_system_language() == LANG_EN  # "C" is skipped, LANG decides


def test_core_does_not_use_the_deprecated_locale_api():
    assert "getdefaultlocale" not in (ROOT / "core" / "i18n.py").read_text(encoding="utf-8")


def test_resolve_language():
    assert resolve_language(LANG_ES, "en") == "es"
    assert resolve_language(LANG_EN, "es") == "en"
    assert resolve_language(LANG_AUTO, "es") == "es"
    assert resolve_language(LANG_AUTO, "en") == "en"
    assert resolve_language("klingon", "es") == "es"  # garbage in the file behaves like auto
    assert resolve_language(None, "es") == "es"


def test_qt_language_from_names_prefers_the_first_supported_preference():
    assert i18n_qt.language_from_names(["pt-BR", "es-UY", "en-US"]) == "es"
    assert i18n_qt.language_from_names(["en-US", "es-ES"]) == "en"
    assert i18n_qt.language_from_names(["fr-FR"]) == "en"
    assert i18n_qt.language_from_names([]) == "en"


def test_system_language_is_a_supported_code(qapp):
    assert i18n_qt.system_language() in i18n.SUPPORTED_LANGUAGES


# ----------------------------------------------------------------------------------------------------------------- #
# Switching and Qt's own translations
# ----------------------------------------------------------------------------------------------------------------- #


def test_apply_language_resolves_auto_and_remembers_the_setting(qapp, monkeypatch):
    monkeypatch.setattr(i18n_qt, "system_language", lambda: "es")
    assert i18n_qt.apply_language(LANG_AUTO, announce=False) == "es"
    assert i18n_qt.current_setting() == LANG_AUTO
    assert i18n.get_language() == "es"
    assert i18n_qt.apply_language("en", announce=False) == "en"
    assert i18n_qt.current_setting() == "en"
    assert i18n_qt.apply_language("garbage", announce=False) == "es"  # unknown setting = auto
    assert i18n_qt.current_setting() == LANG_AUTO


def _button_texts() -> list[str]:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    return [b.text() for b in box.buttons()]


def test_qt_standard_buttons_follow_the_language(qapp):
    i18n_qt.apply_language("es", announce=False)
    assert _button_texts() == ["Aceptar", "Cancelar"]
    i18n_qt.apply_language("en", announce=False)
    assert _button_texts() == ["OK", "Cancel"]
    assert i18n_qt._qt_translators == []  # English leaves no translator behind
    i18n_qt.apply_language("es", announce=False)
    i18n_qt.apply_language("es", announce=False)
    assert len(i18n_qt._qt_translators) == 1  # switching twice does not stack translators


def test_bundled_qt_catalog_is_shipped_and_loadable(qapp):
    qm = ROOT / "locale" / "qt" / "qtbase_es.qm"
    assert qm.is_file() and qm.stat().st_size > 10_000
    assert i18n_qt.install_qt_translators("es") is True
    assert QCoreApplication.translate("QPlatformTheme", "Cancel") == "Cancelar"


def test_qt_catalog_falls_back_to_pyside_when_the_bundled_copy_is_missing(qapp, tmp_path):
    i18n.set_locale_dir(tmp_path)  # no locale/qt here: PySide's own translations folder is used
    assert i18n_qt.install_qt_translators("es") is True


def test_language_choices_start_with_auto(qapp):
    i18n_qt.apply_language("es", announce=False)
    assert i18n_qt.language_choices() == [("auto", "Automático (sistema)"), ("en", "English"), ("es", "Español")]
    i18n_qt.apply_language("en", announce=False)
    assert i18n_qt.language_choices()[0] == ("auto", "Auto (system)")


# ----------------------------------------------------------------------------------------------------------------- #
# Bindings
# ----------------------------------------------------------------------------------------------------------------- #


def test_bind_text_sets_now_and_after_every_switch(qapp):
    button = QPushButton()
    label = QLabel()
    i18n_qt.apply_language("en", announce=False)
    i18n_qt.bind_text(button, "setText", "Search")
    i18n_qt.bind_text(label, "setText", "Signed in as {user}", user="Lucky")
    assert (button.text(), label.text()) == ("Search", "Signed in as Lucky")
    i18n_qt.apply_language("es")
    assert (button.text(), label.text()) == ("Buscar", "Sesión iniciada como Lucky")
    i18n_qt.apply_language("en")
    assert (button.text(), label.text()) == ("Search", "Signed in as Lucky")


def test_bind_accepts_a_factory_and_a_setter_function(qapp):
    from PySide6.QtWidgets import QComboBox

    combo = QComboBox()
    combo.addItems(["x", "y"])
    i18n_qt.apply_language("en", announce=False)
    i18n_qt.bind(combo, lambda w, text: w.setItemText(1, text), lambda: i18n.t("Search"))
    assert combo.itemText(1) == "Search"
    i18n_qt.apply_language("es")
    assert combo.itemText(1) == "Buscar"


def test_binding_again_replaces_the_old_one(qapp):
    button = QPushButton()
    i18n_qt.apply_language("en", announce=False)
    i18n_qt.bind_text(button, "setText", "Search")
    i18n_qt.bind_text(button, "setText", "Plan")
    i18n_qt.apply_language("es")
    assert button.text() == "Plan"


def test_deleted_widgets_are_dropped_quietly(qapp):
    import shiboken6

    gone = QPushButton()  # the C++ object is deleted while the Python wrapper is still alive
    i18n_qt.bind_text(gone, "setText", "Search")
    shiboken6.delete(gone)
    collected = QPushButton()  # the Python wrapper is collected
    i18n_qt.bind_text(collected, "setText", "Search")
    del collected
    gc.collect()
    i18n_qt.apply_language("es")  # must not raise on either dead widget
    assert not any(ref() is None or ref() is gone for ref, _s, _f in i18n_qt._bindings.values())


# ----------------------------------------------------------------------------------------------------------------- #
# Locale-aware formatting
# ----------------------------------------------------------------------------------------------------------------- #


def test_numbers_follow_the_shown_language_not_the_os(qapp):
    i18n_qt.apply_language("en", announce=False)
    assert i18n_qt.format_number(1234.56, 1) == "1234.6"
    assert i18n_qt.format_number(2, 0) == "2"
    i18n_qt.apply_language("es", announce=False)
    assert i18n_qt.format_number(1234.56, 1) == "1234,6"
    assert i18n_qt.format_number(1234567.5, 1) == "1234567,5"  # never grouped
    assert i18n_qt.format_number(0.5, 2) == "0,50"


def test_dates_follow_the_shown_language(qapp):
    day = dt.date(2026, 10, 30)
    i18n_qt.apply_language("en", announce=False)
    assert i18n_qt.format_date(day) == "10/30/26"
    i18n_qt.apply_language("es", announce=False)
    assert i18n_qt.format_date(day) == "30/10/26"
    assert "octubre" in i18n_qt.format_date(day, long=True)
    assert i18n_qt.format_datetime(dt.datetime(2026, 10, 30, 14, 5, 9)).startswith("30/10/26 14:05")


def test_human_size_uses_the_language_decimal_mark(qapp):
    from qt_ui.tabs.plan import human_size

    i18n_qt.apply_language("en", announce=False)
    assert human_size(1_400_000_000) == "1.4 GB"
    i18n_qt.apply_language("es", announce=False)
    assert human_size(1_400_000_000) == "1,4 GB"


# ----------------------------------------------------------------------------------------------------------------- #
# Packaging: the frozen build must find the catalogs
# ----------------------------------------------------------------------------------------------------------------- #


def test_selftest_passes_with_the_shipped_catalogs(qapp, capsys):
    import luckytwitch_qt

    assert luckytwitch_qt.i18n_selftest() == 0
    assert "i18n ok" in capsys.readouterr().out


def test_selftest_fails_loudly_when_the_catalog_is_not_bundled(qapp, capsys, tmp_path):
    import luckytwitch_qt

    i18n.set_locale_dir(tmp_path)
    assert luckytwitch_qt.i18n_selftest() == 1
    assert "Spanish catalog not found" in capsys.readouterr().out


def test_selftest_flag_is_handled_by_main(monkeypatch, qapp):
    import luckytwitch_qt

    monkeypatch.setattr(luckytwitch_qt, "i18n_selftest", lambda: 7)
    assert luckytwitch_qt.main(["luckytwitch", "--i18n-selftest"]) == 7


@pytest.mark.parametrize("script", ["build_windows.bat", "build_mac.sh", "build_linux.sh"])
def test_build_scripts_bundle_the_locale_folder(script):
    assert "--include-data-dir=locale=locale" in (ROOT / script).read_text(encoding="utf-8")


def test_workflow_checks_catalogs_and_smoke_tests_the_frozen_build():
    text = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    assert "tools/i18n.py check" in text
    assert text.count("--i18n-selftest") >= 3  # Windows, macOS and Linux binaries
