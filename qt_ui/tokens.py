"""Design system tokens for Phase 9: space, radius, typography scale, and surfaces.

Plain constants with no Qt dependency so they can be imported anywhere and injected
into the QSS generator template.
"""

from __future__ import annotations

# --- Spacing Scale (px) --- #
SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_6 = 24
SPACE_8 = 32

# --- Corner Radius Scale (px) --- #
RADIUS_INPUT = 4
RADIUS_CHIP = 4
RADIUS_BUTTON = 6
RADIUS_CARD = 8
RADIUS_PILL = 999

# --- Typography Scale (pt) --- #
FONT_SIZE_CAPTION = 9
FONT_SIZE_BODY = 10
FONT_SIZE_ROW = 11
FONT_SIZE_SECTION = 13
FONT_SIZE_TITLE = 16

# --- Motion Duration Tokens (ms) --- #
DURATION_INSTANT = 0
DURATION_MICRO = 80
DURATION_FAST = 140
DURATION_NORMAL = 200
DURATION_ENTER = 240
DURATION_PULSE = 1200

# Mapping for QSS template substitution
DESIGN_TOKENS = {
    "S_1": str(SPACE_1),
    "S_2": str(SPACE_2),
    "S_3": str(SPACE_3),
    "S_4": str(SPACE_4),
    "S_6": str(SPACE_6),
    "S_8": str(SPACE_8),
    "R_INPUT": str(RADIUS_INPUT),
    "R_CHIP": str(RADIUS_CHIP),
    "R_BTN": str(RADIUS_BUTTON),
    "R_CARD": str(RADIUS_CARD),
    "R_PILL": str(RADIUS_PILL),
    "FONT_CAPTION": str(FONT_SIZE_CAPTION),
    "FONT_BODY": str(FONT_SIZE_BODY),
    "FONT_ROW": str(FONT_SIZE_ROW),
    "FONT_SECTION": str(FONT_SIZE_SECTION),
    "FONT_TITLE": str(FONT_SIZE_TITLE),
}
