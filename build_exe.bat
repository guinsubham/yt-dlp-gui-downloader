@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher "py" was not found. Install Python 3.10+ from python.org and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

echo Creating virtual environment...
py -3 -m venv .venv
if errorlevel 1 goto fail

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto fail

python -m pip install -r requirements.txt
if errorlevel 1 goto fail

echo Building standalone EXE...
pyinstaller --noconfirm --clean YT-DLP-GUI.spec
if errorlevel 1 goto fail

echo.
echo Build complete.
echo EXE location: %cd%\dist\YT-DLP-GUI.exe
echo.
pause
exit /b 0

:fail
echo.
echo Build failed. Read the error above.
pause
exit /b 1
