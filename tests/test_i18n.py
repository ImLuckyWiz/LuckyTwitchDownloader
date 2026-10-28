"""Tests for Phase F4: Spanish translation catalog and i18n support."""

from __future__ import annotations

import os

from core.i18n import (
    DEFAULT_LANGUAGE,
    LANG_EN,
    LANG_ES,
    SUPPORTED_LANGUAGES,
    TRANSLATIONS_ES,
    extract_placeholders,
    get_language,
    get_system_language,
    set_language,
    t,
)


def test_supported_languages():
    assert LANG_EN in SUPPORTED_LANGUAGES
    assert LANG_ES in SUPPORTED_LANGUAGES
    assert SUPPORTED_LANGUAGES[LANG_ES] == "Español"
    assert SUPPORTED_LANGUAGES[LANG_EN] == "English"


def test_set_and_get_language():
    try:
        set_language(LANG_ES)
        assert get_language() == LANG_ES
        set_language(LANG_EN)
        assert get_language() == LANG_EN
        # Unsupported code falls back to default
        set_language("fr")
        assert get_language() == DEFAULT_LANGUAGE
    finally:
        set_language(LANG_EN)


def test_t_function_translates_and_formats():
    try:
        set_language(LANG_ES)
        assert t("Plan") == "Plan"
        assert t("Search") == "Buscar"
        assert t("Queue & log") == "Cola y registros"
        assert t("Start queue") == "Iniciar cola"
        assert t("Cancel current") == "Cancelar actual"
        assert t("Signed in as {user}", user="Lucky") == "Sesión iniciada como Lucky"

        # Key not in catalog falls back to original text
        assert t("Untranslated message") == "Untranslated message"

        set_language(LANG_EN)
        assert t("Search") == "Search"
        assert t("Signed in as {user}", user="Lucky") == "Signed in as Lucky"
    finally:
        set_language(LANG_EN)


def test_all_keys_have_valid_translations():
    assert len(TRANSLATIONS_ES) > 30
    for en_key, es_val in TRANSLATIONS_ES.items():
        assert isinstance(en_key, str) and en_key.strip()
        assert isinstance(es_val, str) and es_val.strip()


def test_placeholders_match_across_all_translations():
    """Ensure that every translated string preserves exact formatting placeholders."""
    for en_text, es_text in TRANSLATIONS_ES.items():
        en_placeholders = extract_placeholders(en_text)
        es_placeholders = extract_placeholders(es_text)
        assert en_placeholders == es_placeholders, (
            f"Placeholder mismatch for '{en_text}': "
            f"English has {en_placeholders}, Spanish has {es_placeholders}"
        )


def test_get_system_language_detects_es(monkeypatch):
    monkeypatch.setenv("LANG", "es_ES.UTF-8")
    assert get_system_language() == LANG_ES

    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert get_system_language() == LANG_EN
