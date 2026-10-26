"""First-Run Welcome & Quick Setup experience package."""

from __future__ import annotations

from qt_ui.welcome.background import AnimatedCanvas
from qt_ui.welcome.overlay import WelcomeOverlay
from qt_ui.welcome.setup_card import QuickSetupCard

__all__ = ["AnimatedCanvas", "QuickSetupCard", "WelcomeOverlay"]
