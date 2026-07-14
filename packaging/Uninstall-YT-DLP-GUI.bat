@echo off
setlocal EnableExtensions
title Uninstall YT-DLP GUI Downloader

set "INSTALL_DIR=%LOCALAPPDATA%\Programs\YT-DLP-GUI"
set "START_MENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\YT-DLP GUI Downloader"
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "TASKKILL=%SystemRoot%\System32\taskkill.exe"

if not exist "%POWERSHELL%" (
    echo ERROR: Windows PowerShell could not be found in the system directory.
    pause
    exit /b 1
)

if not exist "%TASKKILL%" (
    echo ERROR: The Windows process manager could not be found in the system directory.
    pause
    exit /b 1
)

echo Uninstalling YT-DLP GUI Downloader...
"%TASKKILL%" /IM YT-DLP-GUI.exe /F >nul 2>&1

"%POWERSHELL%" -NoProfile -Command "$desktop=[Environment]::GetFolderPath('Desktop'); Remove-Item -LiteralPath (Join-Path $desktop 'YT-DLP GUI Downloader.lnk') -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $env:START_MENU_DIR -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\YT-DLP-GUI' -Recurse -Force -ErrorAction SilentlyContinue"

echo YT-DLP GUI Downloader was removed.
start "" /b "%POWERSHELL%" -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Remove-Item -LiteralPath $env:INSTALL_DIR -Recurse -Force -ErrorAction SilentlyContinue"
exit /b 0
