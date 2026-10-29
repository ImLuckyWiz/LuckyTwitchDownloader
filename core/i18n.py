"""Internationalization (i18n): gettext catalogs with English as the message ID.

The call sites are ``t("English text")``; the English text is the key of the catalog, so English needs no catalog
at all. Other languages live in ``locale/<lang>/LC_MESSAGES/luckytwitch.mo`` (compiled from the ``.po`` next to it)
and are loaded with the standard library ``gettext`` (no extra runtime dependency, no Qt: ``core/`` may call
``t()`` too). A message that is missing from a catalog falls back to the English text instead of failing.

Helpers:

* ``t(text, **params)``: translate and fill ``{placeholders}``.
* ``tn(singular, plural, n, **params)``: plural forms (``n`` is also available as ``{n}``).
* ``tc(context, text, **params)``: same word, different meaning (``tc("verb", "Plan")``).
* ``N_(text)``: marks a string for extraction and returns it unchanged; translate it later with ``t(variable)``.

Tooling (extract / update / compile / check) lives in ``tools/i18n.py`` and needs Babel (dev only).
"""

from __future__ import annotations

import gettext
import locale
import os
import re
from pathlib import Path
from typing import Any

from core.resources import resource_path

LANG_EN = "en"
LANG_ES = "es"

SUPPORTED_LANGUAGES = {
    LANG_EN: "English",
    LANG_ES: "Español",
}

DEFAULT_LANGUAGE = LANG_EN

DOMAIN = "luckytwitch"
LOCALE_DIR: Path = resource_path("locale")

_current_language = DEFAULT_LANGUAGE
_translations: gettext.NullTranslations = gettext.NullTranslations()
_cache: dict[str, gettext.NullTranslations] = {}


def set_locale_dir(path: str | os.PathLike[str]) -> None:
    """Point the loader at another ``locale`` folder (used by tests) and re-load the active language."""
    global LOCALE_DIR
    LOCALE_DIR = Path(path)
    _cache.clear()
    set_language(_current_language)


def _load(lang: str) -> gettext.NullTranslations:
    """Return the translations object of ``lang`` (English or a missing catalog: the null object, keys pass through)."""
    if lang == LANG_EN:
        return gettext.NullTranslations()
    cached = _cache.get(lang)
    if cached is not None:
        return cached
    try:
        tr: gettext.NullTranslations = gettext.translation(DOMAIN, localedir=str(LOCALE_DIR), languages=[lang])
    except OSError:  # no .mo for this language, or a corrupt one: show English rather than crash
        tr = gettext.NullTranslations()
    _cache[lang] = tr
    return tr


def get_system_language() -> str:
    """Detect system language from environment or locale. Returns 'es' or 'en'."""
    try:
        lang = os.environ.get("LANG", "") or os.environ.get("LC_ALL", "")
        if not lang:
            loc = locale.getdefaultlocale()[0]
            if loc:
                lang = loc
        if lang and lang.lower().startswith("es"):
            return LANG_ES
    except Exception:
        pass
    return LANG_EN


def set_language(lang: str) -> None:
    """Set active interface language ('en' or 'es'); an unsupported code falls back to English."""
    global _current_language, _translations
    _current_language = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    _translations = _load(_current_language)


def get_language() -> str:
    """Get active interface language code ('en' or 'es')."""
    return _current_language


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def extract_placeholders(text: str) -> set[str]:
    """Extract format placeholders like {name} or {0} from text."""
    return set(_PLACEHOLDER_RE.findall(text))


def _fill(text: str, params: dict[str, Any]) -> str:
    """Fill ``{placeholders}``; a catalog entry with a wrong placeholder must not crash the UI, so it is shown as is."""
    if not params:
        return text
    try:
        return text.format(**params)
    except (KeyError, IndexError, ValueError):
        return text


def t(text: str, **kwargs: Any) -> str:
    """Translate user-facing text to the active language and format placeholders."""
    # gettext("") returns the catalog header, so the empty string must never reach it
    result = _translations.gettext(text) if text else text
    return _fill(result, kwargs)


def tn(singular: str, plural: str, n: int, **kwargs: Any) -> str:
    """Plural-aware translation: ``tn("{n} clip", "{n} clips", count)``; ``{n}`` is always filled with ``n``."""
    kwargs["n"] = n
    return _fill(_translations.ngettext(singular, plural, n), kwargs)


def tc(context: str, text: str, **kwargs: Any) -> str:
    """Translation with a context, for words that mean different things: ``tc("verb", "Plan")`` vs the tab name."""
    return _fill(_translations.pgettext(context, text), kwargs)


def N_(text: str) -> str:
    """Mark ``text`` for extraction without translating it now (``TABS = (N_("Plan"), ...)``; later ``t(name)``)."""
    return text
