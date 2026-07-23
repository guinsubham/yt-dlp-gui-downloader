@echo off
setlocal EnableExtensions
title Uninstall YT-DLP GUI Downloader

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "UNINSTALLER=%~dp0Uninstall-YT-DLP-GUI.ps1"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\YT-DLP-GUI"
set "INSTALLED_EXE=%INSTALL_DIR%\YT-DLP-GUI.exe"
set "START_MENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\YT-DLP GUI Downloader"

if not exist "%POWERSHELL%" (
    echo ERROR: Windows PowerShell could not be found in the system directory.
    pause
    exit /b 1
)

if exist "%UNINSTALLER%" (
    "%POWERSHELL%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%UNINSTALLER%"
    if errorlevel 1 (
        pause
        exit /b 1
    )
    exit /b 0
)

rem Compatibility path for an installation upgraded by the legacy updater.
"%POWERSHELL%" -NoLogo -NoProfile -NonInteractive -Command "$target=$env:INSTALLED_EXE; Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.Name -eq 'YT-DLP-GUI.exe' -and $_.ExecutablePath -and [StringComparer]::OrdinalIgnoreCase.Equals($_.ExecutablePath,$target) } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; $desktop=[Environment]::GetFolderPath('Desktop'); Remove-Item -LiteralPath (Join-Path $desktop 'YT-DLP GUI Downloader.lnk') -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath $env:START_MENU_DIR -Recurse -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\YT-DLP-GUI' -Recurse -Force -ErrorAction SilentlyContinue; $cleanup='Start-Sleep -Seconds 2; Remove-Item -LiteralPath ''' + $env:INSTALL_DIR.Replace('''','''''') + ''' -Recurse -Force -ErrorAction SilentlyContinue'; $encoded=[Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($cleanup)); Start-Process -FilePath $env:POWERSHELL -WindowStyle Hidden -ArgumentList '-NoProfile','-EncodedCommand',$encoded"
if errorlevel 1 (
    pause
    exit /b 1
)
exit /b 0
