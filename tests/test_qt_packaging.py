"""Phase 8: packaging scripts (Nuitka, Inno Setup, macOS bundle), CI workflow, release notes, and pre-release isolation."""

from __future__ import annotations

from pathlib import Path

import pytest

from core import paths
from qt_ui import theme

ROOT = Path(__file__).resolve().parent.parent


def test_build_scripts_use_the_icon():
    assert "assets\\icon.ico" in (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    assert "assets/icon.icns" in (ROOT / "build_mac.sh").read_text(encoding="utf-8")
    assert "SetupIconFile=assets\\icon.ico" in (ROOT / "installer.iss").read_text(encoding="utf-8")


def test_build_scripts_package_the_qt_entry_point_and_collect_qt_modules():
    win = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    mac = (ROOT / "build_mac.sh").read_text(encoding="utf-8")
    for script in (win, mac):
        assert "luckytwitch_qt.py" in script
        assert "luckytwitch_downloader.py" not in script
        assert "nuitka" in script.lower()
        assert "--include-package=core" in script
        assert "--include-package=qt_ui" in script
        assert "--include-package=requests" in script
        assert "--include-module=luckytwitch_engine" in script
        assert "--include-module=weblink" in script
        assert "version.txt" in script


def test_build_scripts_exclude_unused_qt_modules_and_tkinter():
    win = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    mac = (ROOT / "build_mac.sh").read_text(encoding="utf-8")
    expected_excludes = (
        "tkinter",
        "_tkinter",
        "pytest",
    )
    for script in (win, mac):
        assert "--enable-plugin=pyside6" in script
        for mod in expected_excludes:
            assert f"--nofollow-import-to={mod}" in script, mod


def test_build_windows_sanitizes_pe_version_for_nuitka():
    win = (ROOT / "build_windows.bat").read_text(encoding="utf-8")
    assert "--product-version=%PRODUCT_VER%" in win
    assert "--file-version=%PRODUCT_VER%" in win

    import re

    def sanitize(ver: str) -> str:
        nums = [str(min(int(n), 65535)) for n in re.findall(r"\d+", ver)[:4]] or ["1", "0"]
        return ".".join(nums)

    assert sanitize("v0.8.0-beta") == "0.8.0"
    assert sanitize("v0.8.0-beta.1") == "0.8.0.1"
    assert sanitize("v2.0.0") == "2.0.0"
    assert sanitize("1.0") == "1.0"
    assert sanitize("") == "1.0"


def test_requirements_include_pyside6():
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    req_dev = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "PySide6==6.12.0" in req
    assert "pytest-qt" in req_dev
    assert "nuitka" in req


def test_macos_build_script_registers_the_luckytwitch_scheme_before_codesign():
    mac = (ROOT / "build_mac.sh").read_text(encoding="utf-8")
    plist_idx = mac.index("CFBundleURLSchemes")
    scheme_idx = mac.index("string luckytwitch")
    sign_idx = mac.index("codesign --force --deep --sign")
    assert plist_idx < scheme_idx < sign_idx
    assert 'BUNDLE_ID="com.luckytwitch.app.beta"' in mac
    assert 'BUNDLE_ID="com.luckytwitch.app"' in mac


def test_installer_isolates_prereleases_and_keeps_stable_identity():
    iss = (ROOT / "installer.iss").read_text(encoding="utf-8")
    assert '#if Pos("-", AppVersion) > 0' in iss
    # Stable AppId and folder preserved so 2.0 upgrades 1.x in place
    assert "{{6E2B6B0C-3F0D-4C57-9B6A-1A7C2E0D4F11}" in iss
    assert '#define EffectiveDirName "LuckyTwitch"' in iss
    # Pre-release gets its own AppId and install folder
    assert "{{9C4A8D2E-7B1F-4E63-8A5D-3F2E1C9B7D44}" in iss
    assert '#define EffectiveDirName "LuckyTwitch-Beta"' in iss
    assert '#define EffectiveAppName "LuckyTwitch (Beta)"' in iss


@pytest.mark.parametrize(
    "version, expected_pre",
    [
        ("", False),
        ("1.0", False),
        ("v2.0.0", False),
        ("2.0.0", False),
        ("v0.8.0-beta.1", True),
        ("v0.7.0-alpha.1", True),
        ("0.8.0-rc.1", True),
    ],
)
def test_paths_resolve_data_dir_and_app_id_for_stable_and_prerelease(version, expected_pre):
    assert paths.is_prerelease_version(version) is expected_pre
    # From source (frozen=False), DATA_DIR is always APP_DIR
    assert paths.resolve_data_dir(frozen=False, version=version) == paths.APP_DIR
    # Packaged (frozen=True): stable uses user_data_dir(), pre-release uses sibling -beta folder
    base = paths.user_data_dir()
    resolved = paths.resolve_data_dir(frozen=True, version=version)
    if expected_pre:
        assert resolved == base.with_name(base.name + "-beta")
        assert resolved != base
        assert paths.resolve_app_user_model_id(version) == "LuckyTwitch.Downloader.Beta"
    else:
        assert resolved == base
        assert paths.resolve_app_user_model_id(version) == "LuckyTwitch.Downloader"


def test_read_bundled_version_reads_version_file_when_present(tmp_path, monkeypatch):
    ver_file = tmp_path / "version.txt"
    monkeypatch.setattr(paths, "resource_path", lambda *parts: tmp_path.joinpath(*parts))
    assert paths.read_bundled_version() == ""
    ver_file.write_text("v0.8.0-beta.1\n", encoding="utf-8")
    assert paths.read_bundled_version() == "v0.8.0-beta.1"
    assert theme.APP_ID == "LuckyTwitch.Downloader"  # running from source


def test_ci_workflow_runs_pytest_offscreen_and_passes_version_to_both_builders():
    yml = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    assert "QT_QPA_PLATFORM: offscreen" in yml
    assert "requirements-dev.txt" in yml
    assert "python -m pytest tests" in yml
    assert "build_windows.bat" in yml
    assert "bash build_mac.sh" in yml


def test_release_notes_have_top_entries_for_v2():
    main_notes = (ROOT / "RELEASE_NOTES.md").read_text(encoding="utf-8").splitlines()
    assert main_notes[0].strip().startswith("## v2.")
    assert any(line.strip() == "## v2.0.0" for line in main_notes)


def test_is_frozen_detection(monkeypatch):
    monkeypatch.delattr(paths.sys, "frozen", raising=False)
    assert paths.is_frozen() is False
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)
    assert paths.is_frozen() is True
    monkeypatch.delattr(paths.sys, "frozen", raising=False)
    monkeypatch.setitem(paths.__dict__, "__compiled__", True)
    assert paths.is_frozen() is True
