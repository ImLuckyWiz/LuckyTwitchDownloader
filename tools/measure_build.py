"""Measure startup time (Qt vs tkinter) and packaged build/installer sizes for Phase 8.

Usage:
    python tools/measure_build.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _time_command(code: str, env_extra: dict[str, str] | None = None, runs: int = 3) -> list[float]:
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    times: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        elapsed = time.perf_counter() - t0
        if proc.returncode != 0:
            raise RuntimeError(f"Probe failed ({proc.returncode}): {proc.stderr.strip()}")
        times.append(elapsed)
    return times


def _dir_size_bytes(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def main() -> int:
    qt_probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen'); "
        "from luckytwitch_qt import LuckyApplication; "
        "from qt_ui.theme import apply_theme, set_app_icon; "
        "from qt_ui.main_window import MainWindow; "
        "app = LuckyApplication([]); apply_theme(app); set_app_icon(app); "
        "w = MainWindow(settings={}, client=None); w.show(); app.processEvents(); w.close()"
    )
    tk_probe = (
        "import tkinter as tk, luckytwitch_downloader as dl; "
        "dl.ensure_tools = lambda *a, **k: None; dl.make_client = lambda: None; "
        "r = tk.Tk(); r.withdraw(); dl.apply_dark_theme(r); app = dl.App(r); r.update_idletasks(); "
        "[r.after_cancel(i) for i in r.tk.call('after', 'info')]; r.destroy()"
    )

    print("=== Startup Time (source, 3 runs) ===")
    qt_times = _time_command(qt_probe)
    print(f"PySide6 (luckytwitch_qt.py):       min={min(qt_times)*1000:.0f} ms  median={sorted(qt_times)[1]*1000:.0f} ms  runs={[round(t*1000) for t in qt_times]} ms")
    try:
        tk_times = _time_command(tk_probe)
        print(f"tkinter (luckytwitch_downloader.py): min={min(tk_times)*1000:.0f} ms  median={sorted(tk_times)[1]*1000:.0f} ms  runs={[round(t*1000) for t in tk_times]} ms")
    except Exception as exc:  # noqa: BLE001
        print(f"tkinter probe skipped: {exc}")

    print("\n=== Packaged Output Sizes (dist/) ===")
    dist_dir = ROOT / "dist" / "LuckyTwitch"
    installer = ROOT / "dist" / "LuckyTwitch-Setup.exe"
    if dist_dir.is_dir():
        mb = _dir_size_bytes(dist_dir) / (1024 * 1024)
        print(f"Portable folder (dist/LuckyTwitch): {mb:.1f} MB")
    else:
        print("Portable folder (dist/LuckyTwitch): not built yet (run build_windows.bat)")
    if installer.is_file():
        mb = installer.stat().st_size / (1024 * 1024)
        print(f"Windows installer (dist/LuckyTwitch-Setup.exe): {mb:.1f} MB")
    else:
        print("Windows installer (dist/LuckyTwitch-Setup.exe): not built yet (run build_windows.bat)")
    for dmg in sorted((ROOT / "dist").glob("LuckyTwitch-*.dmg")) if (ROOT / "dist").is_dir() else []:
        mb = dmg.stat().st_size / (1024 * 1024)
        print(f"macOS disk image ({dmg.name}): {mb:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
