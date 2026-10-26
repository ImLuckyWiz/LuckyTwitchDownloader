"""WCAG 2.1 contrast ratio tests for the Phase 9 design system.

Pure-Python calculation of relative luminance and contrast ratios.
Ensures no text or boundary color pair regresses below accessibility thresholds.
"""

from __future__ import annotations

import pytest

from core import palette


def relative_luminance(hex_code: str) -> float:
    """Compute WCAG 2.1 relative luminance for an sRGB hex code (#rrggbb)."""
    hex_code = hex_code.lstrip("#")
    rgb = [int(hex_code[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(color1: str, color2: str) -> float:
    """Compute the contrast ratio between two colors (range 1.0 to 21.0)."""
    l1 = relative_luminance(color1)
    l2 = relative_luminance(color2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_primary_text_contrast():
    # FG (#e6e6e6) must comfortably pass AAA (>7:1) on all dark surfaces
    for surface in (palette.BG, palette.BG2, palette.BG3):
        assert contrast_ratio(palette.FG, surface) >= 7.0


def test_muted_text_contrast():
    # MUTED (#a3a6ad) must pass WCAG AA (>= 4.5:1) on all three dark surfaces
    assert contrast_ratio(palette.MUTED, palette.BG) >= 4.5
    assert contrast_ratio(palette.MUTED, palette.BG2) >= 4.5
    assert contrast_ratio(palette.MUTED, palette.BG3) >= 4.5


def test_accent_button_text_contrast():
    # White on primary ACCENT button
    assert contrast_ratio(palette.WHITE, palette.ACCENT) >= 4.5


def test_accent_text_contrast():
    # ACCENT_TEXT (#b380ff) on raised background BG2
    assert contrast_ratio(palette.ACCENT_TEXT, palette.BG2) >= 4.5


def test_card_border_visibility():
    # BORDER_STRONG must have visible boundary distinction against BG2 (>1.5:1)
    assert contrast_ratio(palette.BORDER_STRONG, palette.BG2) >= 1.5


def test_error_and_success_contrast():
    # ERR and OK labels on base background
    assert contrast_ratio(palette.ERR, palette.BG) >= 4.5
    assert contrast_ratio(palette.OK, palette.BG) >= 4.5
