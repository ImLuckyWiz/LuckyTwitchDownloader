# LuckyTwitch Spanish Localization QA Checklist (Phase I11)

This checklist provides a structured manual and automated verification procedure for ensuring complete, high-quality localization across all tabs, dialogs, widgets, and engine flows.

---

## 1. Automated Verification Checks

Run all verification tools before any release:

```bash
# 1. Run the i18n validator (checks POT sync, MO match, zero untranslated, placeholders, glossary)
python tools/i18n.py check

# 2. Run the i18n test suite
python -m pytest tests/test_i18n.py tests/test_i18n_qt.py tests/test_ui_language.py -v

# 3. Run the frozen-build self test
python luckytwitch_qt.py --i18n-selftest
```

**Expected results:**
- `python tools/i18n.py check` exits with code 0 (`i18n check passed.`).
- Unwrapped UI literals count in `tools/i18n_baseline.json` is `0`.
- All i18n test suites pass with zero failures and zero warnings.

---

## 2. Pseudo-Localization Test Mode

Launch the application in pseudo-localization mode to detect hard-coded (unwrapped) strings, text truncation, and layout overflow:

```bash
python luckytwitch_qt.py --lang pseudo
# or via environment variable:
# LUCKYTWITCH_LANG=pseudo python luckytwitch_qt.py
```

**What to look for:**
- **Untranslated text:** Any string that appears in plain English without `[...]` brackets and accented characters (`ä`, `ë`, `ï`, `ö`, `ü`) is an unwrapped string leak.
- **Clipping / Truncation:** Because pseudo-strings are expanded by ~30%, verify that:
  - Navigation rail buttons do not overflow.
  - Action buttons (`Get info`, `Add to queue`, `Start queue`) remain fully visible.
  - Table headers remain readable.
  - Setting labels and inline badges do not overlap controls.

---

## 3. UI Inspection Walk (Spanish `es`) at Minimum Size (900 × 560 px)

Launch the application in Spanish at the minimum supported window geometry:

```bash
python luckytwitch_qt.py --lang es
```

Resize the window to **900 × 560 px** and review each screen:

### Top Command Bar & Shell
- [ ] URL / ID input placeholder: `Pega un enlace o ID de VOD de Twitch...`
- [ ] Action buttons: `Pegar`, `Obtener información`, `API de Twitch...`, `Historial`
- [ ] Navigation rail tooltips and labels: `Buscar`, `Plan`, `Opciones`, `Cola y registro`
- [ ] Status bar message: `Listo. Pega una URL o ID de VOD y presiona «Obtener información».`

### Tab 1: Plan Tab & Timeline
- [ ] Empty state: `Ningún VOD cargado.`
- [ ] Plan cards: `Puntos de corte`, `Estrategia`, `Resumen de partes`
- [ ] Timeline buttons & tooltips: `Alejar (−)`, `Acercar (+)`, `Ajustar`, `Mostrar todo el VOD (0)`, `Deshacer`, `Rehacer`
- [ ] Strategy options: `Auto (recomendado)`, `Descargar partes directamente`, `Descargar VOD completo y dividir`
- [ ] Action buttons: `Añadir a la cola`, `Añadir e iniciar`

### Tab 2: Search Tab & Watch List
- [ ] Banner: `Inicia sesión con Twitch para buscar streamers y listar sus VODs.`
- [ ] Search input and button: `Streamer:`, `Buscar`
- [ ] Left pane headers: `Resultados`, `Streamers recientes`, `Borrar recientes`
- [ ] Table headers: `Título`, `Fecha`, `Duración`, `Visualizaciones`
- [ ] Action button: `Usar este VOD`
- [ ] Pin button tooltip: `Fijar streamer a la lista de seguimiento` / `Desfijar streamer`

### Tab 3: Options Tab
- [ ] Settings search bar: `Buscar ajustes...`
- [ ] Test bilingual search: typing both Spanish (e.g. `descarga`, `carpeta`) and English (e.g. `download`, `folder`) returns matching setting rows.
- [ ] 7 sections in sidebar: `Salida`, `Cortes`, `Capítulos`, `Premiere Pro`, `Chat`, `Clips`, `Herramientas`
- [ ] Interface section: `Idioma` selector displays `Auto (sistema)`, `English`, `Español`
- [ ] Action buttons: `Examinar...`, `Abrir carpeta`, `Actualizar yt-dlp ahora`, `Abrir carpeta de herramientas`

### Tab 4: Queue & Log Tab
- [ ] Empty state: `No hay nada en la cola todavía`
- [ ] Queue toolbar: `Iniciar cola`, `Cancelar actual`, `Reintentar`, `Quitar seleccionados`, `Limpiar finalizados`
- [ ] Parallel concurrency selector: `1 tarea`, `2 tareas en paralelo`, `3 tareas en paralelo`, `4 tareas en paralelo`
- [ ] Speed limit selector: `Sin límite`, `1 MB/s`, `2 MB/s`, `5 MB/s`, `10 MB/s`, `20 MB/s`
- [ ] Log toolbar: `Todos`, `Advertencias`, `Errores`, `Pausar desplazamiento`, `Guardar registro...`, `Copiar registro`, `Limpiar registro`

### Dialogs & First Run
- [ ] Twitch API Dialog: `Iniciar sesión con Twitch`, `Copiar código`, `Cerrar`
- [ ] History Dialog: `Historial de descargas`, table headers (`Descargado`, `Streamer`, `Título`, `Partes`, `Calidad`, `Acciones`), `Limpiar historial`
- [ ] Update Dialog: `Actualización disponible`, `Actualizar ahora`, `Página de versión`, `Más tarde`
- [ ] Welcome Overlay & Setup Card: `INICIO RÁPIDO (ESENCIALES)`, `Carpeta de descargas:`, `Comenzar a usar LuckyTwitch →`

---

## 4. Dynamic Live Language Switching Test

1. Open **Opciones → Interfaz**.
2. Switch Language from **Español** to **English**.
   - Verify every visible tab title, button, card header, and status text switches immediately to English without restarting the app.
3. Switch Language from **English** to **Español**.
   - Verify all texts immediately switch back to Spanish.
4. Verify standard Qt dialogs (e.g. `QMessageBox`, `QFileDialog`) use localized Spanish buttons (`Aceptar`, `Cancelar`, `Guardar`, `Abrir`).

---

## 5. Visual QA Sign-off
- **Date Verified:**
- **Tester:**
- **Status:** PASS / FAIL
