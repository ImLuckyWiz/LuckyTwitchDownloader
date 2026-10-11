@echo off
REM Build LuckyTwitch for Windows -> dist\LuckyTwitch\LuckyTwitch.exe
REM Needs Python 3.10+ from python.org (with "tcl/tk" ticked, which is the default).
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pip || goto :err
python -m pip install -r requirements.txt || goto :err

python -m PyInstaller --noconfirm --clean --windowed ^
  --name LuckyTwitch ^
  --collect-submodules requests ^
  --hidden-import luckytwitch_engine ^
  luckytwitch_downloader.py || goto :err

echo.
echo Done: dist\LuckyTwitch\LuckyTwitch.exe
echo (zip the whole dist\LuckyTwitch folder to share it)
exit /b 0

:err
echo Build failed.
exit /b 1
