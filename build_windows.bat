@echo off
REM Build LuckyTwitch (PySide6) for Windows:
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

python -m PyInstaller --noconfirm --clean --windowed ^
  --name LuckyTwitch ^
  --icon assets\icon.ico ^
  --add-data "assets;assets" ^
  --add-data "build\version.txt;." ^
  --collect-submodules requests ^
  --collect-submodules core ^
  --collect-submodules qt_ui ^
  --hidden-import luckytwitch_engine ^
  --hidden-import weblink ^
  --exclude-module tkinter ^
  --exclude-module _tkinter ^
  --exclude-module PIL._tkinter_finder ^
  --exclude-module PIL.ImageTk ^
  --exclude-module pytest ^
  --exclude-module PySide6.QtWebEngineCore ^
  --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtWebEngineQuick ^
  --exclude-module PySide6.QtWebChannel ^
  --exclude-module PySide6.QtWebSockets ^
  --exclude-module PySide6.QtQml ^
  --exclude-module PySide6.QtQuick ^
  --exclude-module PySide6.QtQuick3D ^
  --exclude-module PySide6.QtQuickControls2 ^
  --exclude-module PySide6.QtQuickWidgets ^
  --exclude-module PySide6.QtMultimedia ^
  --exclude-module PySide6.QtMultimediaWidgets ^
  --exclude-module PySide6.QtSpatialAudio ^
  --exclude-module PySide6.Qt3DCore ^
  --exclude-module PySide6.Qt3DRender ^
  --exclude-module PySide6.Qt3DInput ^
  --exclude-module PySide6.Qt3DLogic ^
  --exclude-module PySide6.Qt3DExtras ^
  --exclude-module PySide6.Qt3DAnimation ^
  --exclude-module PySide6.QtCharts ^
  --exclude-module PySide6.QtDataVisualization ^
  --exclude-module PySide6.QtGraphs ^
  --exclude-module PySide6.QtGraphsWidgets ^
  --exclude-module PySide6.QtPdf ^
  --exclude-module PySide6.QtPdfWidgets ^
  --exclude-module PySide6.QtSql ^
  --exclude-module PySide6.QtNetwork ^
  --exclude-module PySide6.QtNetworkAuth ^
  --exclude-module PySide6.QtSvg ^
  --exclude-module PySide6.QtSvgWidgets ^
  --exclude-module PySide6.QtOpenGL ^
  --exclude-module PySide6.QtOpenGLWidgets ^
  --exclude-module PySide6.QtPrintSupport ^
  --exclude-module PySide6.QtDesigner ^
  --exclude-module PySide6.QtHelp ^
  --exclude-module PySide6.QtUiTools ^
  --exclude-module PySide6.QtXml ^
  --exclude-module PySide6.QtTest ^
  --exclude-module PySide6.QtPositioning ^
  --exclude-module PySide6.QtLocation ^
  --exclude-module PySide6.QtSensors ^
  --exclude-module PySide6.QtSerialPort ^
  --exclude-module PySide6.QtSerialBus ^
  --exclude-module PySide6.QtBluetooth ^
  --exclude-module PySide6.QtNfc ^
  --exclude-module PySide6.QtRemoteObjects ^
  --exclude-module PySide6.QtScxml ^
  --exclude-module PySide6.QtStateMachine ^
  --exclude-module PySide6.QtTextToSpeech ^
  --exclude-module PySide6.QtVirtualKeyboard ^
  --exclude-module PySide6.QtShaderTools ^
  --exclude-module PySide6.QtDBus ^
  luckytwitch_qt.py || goto :err

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
