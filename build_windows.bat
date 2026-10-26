@echo off
REM Build LuckyTwitch (PySide6) for Windows with Nuitka:
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

if not exist build mkdir build
> build\version.txt echo %VER%

if exist dist\LuckyTwitch rmdir /s /q dist\LuckyTwitch
if exist dist\LuckyTwitch.dist rmdir /s /q dist\LuckyTwitch.dist

python -m nuitka --mode=standalone ^
  --enable-plugin=pyside6 ^
  --windows-console-mode=disable ^
  --windows-icon-from-ico=assets\icon.ico ^
  --company-name=LuckyTwitch ^
  --product-name=LuckyTwitch ^
  --product-version=%VER% ^
  --output-dir=dist ^
  --output-folder-name=LuckyTwitch ^
  --output-filename=LuckyTwitch.exe ^
  --include-data-dir=assets=assets ^
  --include-data-files=build\version.txt=version.txt ^
  --include-package=core ^
  --include-package=qt_ui ^
  --include-package=requests ^
  --include-module=luckytwitch_engine ^
  --include-module=weblink ^
  --nofollow-import-to=tkinter ^
  --nofollow-import-to=_tkinter ^
  --nofollow-import-to=pytest ^
  --assume-yes-for-downloads ^
  --update-check=never ^
  luckytwitch_qt.py || goto :err

if exist dist\LuckyTwitch.dist (
  ren dist\LuckyTwitch.dist LuckyTwitch || goto :err
)

set ISCC=
where iscc >nul 2>nul && set ISCC=iscc
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set ISCC="%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set ISCC="%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
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
