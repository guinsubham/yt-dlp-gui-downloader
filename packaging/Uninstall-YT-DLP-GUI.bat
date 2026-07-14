@echo off
setlocal EnableExtensions
title Uninstall YT-DLP GUI Downloader

set "INSTALL_DIR=%LOCALAPPDATA%\Programs\YT-DLP-GUI"
set "START_MENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\YT-DLP GUI Downloader"

echo Uninstalling YT-DLP GUI Downloader...
taskkill /IM YT-DLP-GUI.exe /F >nul 2>&1

powershell.exe -NoProfile -Command "$desktop=[Environment]::GetFolderPath('Desktop'); Remove-Item -LiteralPath (Join-Path $desktop 'YT-DLP GUI Downloader.lnk') -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $env:START_MENU_DIR -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\YT-DLP-GUI' -Recurse -Force -ErrorAction SilentlyContinue"

echo YT-DLP GUI Downloader was removed.
start "" /b powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Remove-Item -LiteralPath $env:INSTALL_DIR -Recurse -Force -ErrorAction SilentlyContinue"
exit /b 0
