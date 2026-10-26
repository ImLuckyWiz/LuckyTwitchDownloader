"""Unit tests for Phase 9h themed dialogs and accessibility (H1, H2, I1, I2).

Tests:
  - ThemedDialog title, summary, and vector icons
  - Technical error summary extraction and expandable details fold
  - Copy details button to clipboard
  - Modal return values for ask_yes_no and ask_ok_cancel
  - Accessibility labels on shell and timeline icon-only controls
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from qt_ui import dialogs
from qt_ui.dialogs import ThemedDialog
from qt_ui.main_window import MainWindow


def test_themed_dialog_renders_title_and_summary(qtbot):
    dlg = ThemedDialog(None, "Notice", "Everything went smoothly.", icon_name="check")
    qtbot.addWidget(dlg)
    dlg.show()
    assert dlg.windowTitle() == "Notice"
    assert dlg.title_lbl.text() == "Notice"
    assert dlg.summary_lbl.text() == "Everything went smoothly."
    assert dlg.details_edit is None
    dlg.accept()


def test_themed_dialog_multiline_splits_summary_and_details(qtbot):
    multiline_text = "yt-dlp could not read that URL:\nERROR: [generic] 'invalid' is not a valid URL"
    dlg = ThemedDialog(None, "Download Error", multiline_text, icon_name="alert")
    qtbot.addWidget(dlg)
    dlg.show()

    assert dlg.summary_lbl.text() == "yt-dlp could not read that URL:"
    assert dlg.details_edit is not None
    assert dlg.details_edit.toPlainText() == "ERROR: [generic] 'invalid' is not a valid URL"
    assert not dlg.details_edit.isVisible()

    # Toggle details
    dlg.toggle_details_btn.click()
    assert dlg.details_edit.isVisible()
    assert dlg.toggle_details_btn.text() == "Hide details"

    dlg.toggle_details_btn.click()
    assert not dlg.details_edit.isVisible()
    assert dlg.toggle_details_btn.text() == "Show details"
    dlg.accept()


def test_themed_dialog_copy_details_to_clipboard(qtbot):
    dlg = ThemedDialog(None, "Error", "Short summary\nFull traceback line 1\nFull traceback line 2")
    qtbot.addWidget(dlg)
    dlg.show()

    assert dlg.copy_details_btn is not None
    dlg.copy_details_btn.click()
    clip = QApplication.clipboard()
    assert clip.text() == "Full traceback line 1\nFull traceback line 2"
    assert dlg.copy_details_btn.text() == "Copied!"
    dlg.accept()


def test_themed_dialog_buttons_accept_and_reject(qtbot):
    dlg_accept = ThemedDialog(None, "Confirm", "Do you want to continue?", buttons=(("Cancel", "ghost", False), ("OK", "accent", True)))
    qtbot.addWidget(dlg_accept)
    dlg_accept.show()
    # Click OK
    dlg_accept.action_buttons[1].click()
    assert dlg_accept.result() == ThemedDialog.DialogCode.Accepted

    dlg_reject = ThemedDialog(None, "Confirm", "Do you want to cancel?", buttons=(("Cancel", "ghost", False), ("OK", "accent", True)))
    qtbot.addWidget(dlg_reject)
    dlg_reject.show()
    # Click Cancel
    dlg_reject.action_buttons[0].click()
    assert dlg_reject.result() == ThemedDialog.DialogCode.Rejected


def test_accessibility_names_on_icon_buttons(qtbot):
    win = MainWindow(settings={}, client=None)
    qtbot.addWidget(win)

    # Shell rail & command bar buttons
    for btn in win.rail.buttons.values():
        assert bool(btn.accessibleName())
        assert "tab" in btn.accessibleDescription().lower()
    assert win.rail.toggle_btn.accessibleName() == "Toggle navigation sidebar"
    assert win.vod_action_btn.accessibleName() == "Paste VOD URL or clear input"
    assert win.vod_strip.open_btn.accessibleName() == "Open VOD on Twitch in browser"
    assert win.vod_strip.clear_btn.accessibleName() == "Clear loaded VOD"

    # Timeline buttons
    tl = win.tab_plan.timeline
    assert tl.btn_in.accessibleName() == "Zoom in"
    assert tl.btn_out.accessibleName() == "Zoom out"
    assert tl.btn_fit.accessibleName() == "Fit timeline to window"
    assert tl.btn_undo.accessibleName() == "Undo last cut edit"
    assert tl.btn_redo.accessibleName() == "Redo last undone cut edit"
    assert tl.canvas.accessibleName() == "Interactive VOD timeline"

    # Search view mode switcher
    st = win.tab_search
    assert st.list_mode_btn.accessibleName() == "Switch to list table view"
    assert st.grid_mode_btn.accessibleName() == "Switch to grid card view"
