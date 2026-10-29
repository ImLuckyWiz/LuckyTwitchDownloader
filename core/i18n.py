"""Internationalization (i18n) catalog and translation helper.

Lightweight, dictionary-based catalog with English (en) as the source
and Spanish (es) translation for user-facing interface text.
"""

from __future__ import annotations

import locale
import os
import re
from typing import Any

LANG_EN = "en"
LANG_ES = "es"

SUPPORTED_LANGUAGES = {
    LANG_EN: "English",
    LANG_ES: "Español",
}

DEFAULT_LANGUAGE = LANG_EN
_current_language = DEFAULT_LANGUAGE

# Catalog of Spanish translations (source key is English text)
TRANSLATIONS_ES: dict[str, str] = {
    # Navigation & Tabs
    "Plan": "Plan",
    "Search": "Buscar",
    "History": "Historial",
    "Queue & log": "Cola y registros",
    "Options": "Opciones",

    # Common buttons & controls
    "Start queue": "Iniciar cola",
    "Cancel current": "Cancelar actual",
    "Retry": "Reintentar",
    "Move selected waiting job up": "Mover trabajo en espera arriba",
    "Move selected waiting job down": "Mover trabajo en espera abajo",
    "Remove selected": "Eliminar seleccionado",
    "Clear finished": "Limpiar terminados",
    "Open folder": "Abrir carpeta",
    "Clear history": "Limpiar historial",
    "Search VODs": "Buscar VODs",
    "Get info": "Obtener información",
    "Download": "Descargar",
    "Close": "Cerrar",
    "Save": "Guardar",
    "Copy": "Copiar",
    "Clear": "Limpiar",
    "Back": "Atrás",
    "Next": "Siguiente",
    "Finish": "Finalizar",
    "Quit": "Salir",
    "Cancel": "Cancelar",
    "OK": "Aceptar",
    "Load": "Cargar",
    "Refresh": "Actualizar",
    "Apply": "Aplicar",

    # Queue & log
    "Log": "Registro",
    "All": "Todo",
    "Warnings": "Advertencias",
    "Errors": "Errores",
    "Filter log lines…": "Filtrar líneas de registro…",
    "Pause autoscroll": "Pausar desplazamiento automático",
    "Save log…": "Guardar registro…",
    "Copy log": "Copiar registro",
    "Clear log": "Limpiar registro",
    "Nothing queued.": "Nada en cola.",
    "Cancelling…": "Cancelando…",
    "1 job": "1 trabajo",
    "2 parallel jobs": "2 trabajos paralelos",
    "3 parallel jobs": "3 trabajos paralelos",
    "4 parallel jobs": "4 trabajos paralelos",
    "How many queue jobs can run at the same time": "Cuántos trabajos de cola pueden ejecutarse al mismo tiempo",
    "Unlimited speed": "Velocidad ilimitada",
    "Bandwidth limit passed to yt-dlp (--limit-rate)": "Límite de ancho de banda para yt-dlp (--limit-rate)",

    # Status words & summary
    "queued": "en cola",
    "running": "ejecutando",
    "done": "listo",
    "failed": "fallido",
    "cancelled": "cancelado",
    "Downloaded": "Descargado",
    "✓ Downloaded": "✓ Descargado",
    "No downloads yet": "Aún no hay descargas",
    "Finished downloads will appear here with date, parts and folder location.": "Las descargas completadas aparecerán aquí con fecha, partes y ubicación.",

    # History dialog
    "Download History": "Historial de descargas",
    "Date": "Fecha",
    "Streamer": "Streamer",
    "Title": "Título",
    "Parts": "Partes",
    "Quality": "Calidad",
    "Folder": "Carpeta",
    "Clear download history? This cannot be undone.": "¿Limpiar el historial de descargas? Esto no se puede deshacer.",

    # Search & Watch list
    "Past broadcasts": "Emisiones pasadas",
    "Highlights": "Destacados",
    "Uploads": "Subidas",
    "Pin streamer": "Fijar streamer",
    "Unpin streamer": "Desfijar streamer",
    "Pin this streamer to be notified of new VODs": "Fija a este streamer para recibir notificaciones de nuevos VODs",
    "Pinned": "Fijado",

    # Options tab headings & cards
    "Output": "Salida",
    "Where the finished files go and how they are named.": "Dónde se guardan los archivos terminados y cómo se nombran.",
    "Cuts": "Cortes",
    "How the VOD is downloaded and cut into parts.": "Cómo se descarga el VOD y se corta en partes.",
    "Chapters": "Capítulos",
    "Premiere Pro": "Premiere Pro",
    "Markers you can bring into Adobe Premiere Pro next to each part.": "Marcadores que puedes llevar a Adobe Premiere Pro junto a cada parte.",
    "Chat": "Chat",
    "Download the chat that went with the stream, or turn it into a video you can put next to the stream.": "Descarga el chat de la transmisión o conviértelo en un video para superponer.",
    "Clips": "Clips",
    "Used by the «Download only selected clip» button in the Plan tab.": "Usado por el botón «Descargar solo el clip seleccionado» en la pestaña Plan.",
    "Tools": "Herramientas",
    "yt-dlp and ffmpeg do the downloading and cutting.": "yt-dlp y ffmpeg realizan la descarga y el corte.",
    "Language": "Idioma",
    "Interface language": "Idioma de la interfaz",
    "Select language for the user interface": "Selecciona el idioma para la interfaz de usuario",
    "Dark window bar": "Barra de ventana oscura",
    "Use custom dark title bar instead of native frame": "Usar barra de título oscura personalizada en lugar del marco nativo",

    # Dialogs & General
    'VOD URL or ID:': 'URL o ID del VOD:',
    'Paste': 'Pegar',
    'No VOD loaded.': 'Ningún VOD cargado.',
    'Ready. Paste a VOD URL or ID and press «Get info».': 'Listo. Pega una URL o ID de VOD y presiona «Obtener información».',
    'Interface': 'Interfaz',
    'Language and appearance settings.': 'Ajustes de idioma y apariencia.',
    'Select interface language (English / Español).': 'Selecciona el idioma de la interfaz (English / Español).',
    'Twitch API…': 'API de Twitch…',
    'Collapse': 'Colapsar',
    'Language changed': 'Idioma cambiado',
    'Restart LuckyTwitch to apply all changes across the interface.': 'Reinicia LuckyTwitch para aplicar todos los cambios en la interfaz.',
    'Paste from clipboard': 'Pegar desde el portapapeles',
    'Clear VOD field': 'Limpiar campo de VOD',
    'Search streamers': 'Buscar streamers',
    'Add to queue': 'Añadir a la cola',
    'Add & start': 'Añadir e iniciar',
    'Add && start': 'Añadir e iniciar',
    'Select all': 'Seleccionar todo',
    'Invert': 'Invertir',
    'Split at selected clip': 'Dividir en el clip seleccionado',
    'Download only selected clip': 'Descargar solo el clip seleccionado',
    'Queue': 'Cola',
    'Language changed to {lang}. Restart LuckyTwitch to apply all changes across the interface.': 'Idioma cambiado a {lang}. Reinicia LuckyTwitch para aplicar todos los cambios en la interfaz.',
    'Check for yt-dlp updates on startup': 'Comprobar actualizaciones de yt-dlp al iniciar',
    'Recommended: Twitch changes often.': 'Recomendado: Twitch cambia con frecuencia.',
    'Update yt-dlp': 'Actualizar yt-dlp',
    'Update yt-dlp now': 'Actualizar yt-dlp ahora',
    'Download the latest version now.': 'Descargar la versión más reciente ahora.',
    'Tools folder': 'Carpeta de herramientas',
    'Open tools folder': 'Abrir carpeta de herramientas',
    'Where yt-dlp, ffmpeg and TwitchDownloaderCLI are kept.': 'Dónde se guardan yt-dlp, ffmpeg y TwitchDownloaderCLI.',
    'LuckyTwitch updates': 'Actualizaciones de LuckyTwitch',
    'Check for new versions of LuckyTwitch Downloader.': 'Comprobar nuevas versiones de LuckyTwitch Downloader.',
    'Check for new versions of LuckyTwitch': 'Comprobar nuevas versiones de LuckyTwitch',
    'Notifies you when a new release is available on GitHub.': 'Te notifica cuando hay una nueva versión disponible en GitHub.',
    'Version': 'Versión',
    'Check now': 'Comprobar ahora',
    'Check GitHub releases for updates now.': 'Comprobar actualizaciones en GitHub ahora.',
    'Links from web pages': 'Enlaces de páginas web',
    'Open luckytwitch:// links': 'Abrir enlaces luckytwitch://',
    'Use this copy': 'Usar esta copia',
    'These links currently open another copy of LuckyTwitch. Press the button to use this one.': 'Estos enlaces abren actualmente otra copia de LuckyTwitch. Presiona el botón para usar esta.',
    'These links already open this copy of LuckyTwitch.': 'Estos enlaces ya abren esta copia de LuckyTwitch.',
    "Sign in with Twitch": "Iniciar sesión con Twitch",
    "Sign out": "Cerrar sesión",
    "Signed in as {user}": "Sesión iniciada como {user}",
    "Not signed in": "No has iniciado sesión",
    "Check for updates": "Buscar actualizaciones",
    "New version available: {version}": "Nueva versión disponible: {version}",
    "You are using the latest version.": "Estás usando la versión más reciente.",
}


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
    """Set active interface language ('en' or 'es')."""
    global _current_language
    _current_language = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def get_language() -> str:
    """Get active interface language code ('en' or 'es')."""
    return _current_language


_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def extract_placeholders(text: str) -> set[str]:
    """Extract format placeholders like {name} or {0} from text."""
    return set(_PLACEHOLDER_RE.findall(text))


def t(text: str, **kwargs: Any) -> str:
    """Translate user-facing text to the active language and format placeholders."""
    result = text
    if _current_language == LANG_ES:
        result = TRANSLATIONS_ES.get(text, text)
    if kwargs:
        try:
            return result.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return result
    return result
