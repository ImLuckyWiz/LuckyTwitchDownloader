"""The four tabs of the main window. Empty in Phase 1; each later phase fills one in."""

from qt_ui.tabs.options import OptionsTab
from qt_ui.tabs.plan import PlanTab
from qt_ui.tabs.queue import QueueTab
from qt_ui.tabs.search import SearchTab

__all__ = ["SearchTab", "PlanTab", "OptionsTab", "QueueTab"]
