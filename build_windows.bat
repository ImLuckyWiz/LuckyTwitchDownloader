@echo off
REM Build LuckyTwitch for Windows:
REM   dist\LuckyTwitch\LuckyTwitch.exe   (portable folder)
REM   dist\LuckyTwitch-Setup.exe         (installer, if Inno Setup is installed)
REM Usage: build_windows.bat [version]
REM Needs Python 3.10+ from python.org. Installer needs Inno Setup 6 (jrsoftware.org/isdl.php).
setlocal
cd /d "%~dp0"
set VER=%1
if "%VER%"=="" set VER=1.0

python -m pip install --upgrade pip || goto :err
python -m pip install -r requirements.txt || goto :err

python -m PyInstaller --noconfirm --clean --windowed ^
  --name LuckyTwitch ^
  --collect-submodules requests ^
  --collect-submodules ui ^
  --hidden-import luckytwitch_engine ^
  --hidden-import PIL._tkinter_finder ^
  luckytwitch_downloader.py || goto :err

set ISCC=
where iscc >nul 2>nul && set ISCC=iscc
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"

if defined ISCC (
  %ISCC% /DAppVersion=%VER% installer.iss || goto :err
  echo.
  echo Installer: dist\LuckyTwitch-Setup.exe
) else (
  echo.
  echo Inno Setup not found - skipping the installer. Get it from https://jrsoftware.org/isdl.php
)
echo Portable app: dist\LuckyTwitch\LuckyTwitch.exe
exit /b 0

:err
echo Build failed.
exit /b 1
