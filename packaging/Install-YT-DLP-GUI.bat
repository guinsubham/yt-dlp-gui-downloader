@echo off
setlocal EnableExtensions
title Install YT-DLP GUI Downloader

set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "INSTALLER=%~dp0Install-YT-DLP-GUI.ps1"
set "SOURCE_EXE=%~dp0YT-DLP-GUI.exe"
set "SOURCE_UNINSTALLER=%~dp0Uninstall-YT-DLP-GUI.bat"
set "SOURCE_LICENSE=%~dp0LICENSE"
set "SOURCE_NOTICES=%~dp0THIRD_PARTY_NOTICES.md"
set "EXPECTED_HASH=__EXPECTED_HASH__"
set "APP_VERSION=__APP_VERSION__"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\YT-DLP-GUI"
set "INSTALLED_EXE=%INSTALL_DIR%\YT-DLP-GUI.exe"

if not exist "%POWERSHELL%" (
    echo ERROR: Windows PowerShell could not be found in the system directory.
    goto :failed
)

if exist "%INSTALLER%" (
    "%POWERSHELL%" -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%INSTALLER%"
    if errorlevel 1 goto :failed
    exit /b 0
)

rem Compatibility path for updates launched by versions that predate the
rem transactional PowerShell package. The archive and executable are still
rem verified, and the new app materializes bundled third-party licenses.
for %%F in ("%SOURCE_EXE%" "%SOURCE_UNINSTALLER%" "%SOURCE_LICENSE%" "%SOURCE_NOTICES%") do (
    if not exist "%%~F" (
        echo ERROR: The legacy update package is incomplete.
        goto :failed
    )
)

"%POWERSHELL%" -NoLogo -NoProfile -NonInteractive -Command "if ((Get-FileHash -LiteralPath $env:SOURCE_EXE -Algorithm SHA256).Hash -ne $env:EXPECTED_HASH) { exit 2 }"
if errorlevel 1 (
    echo ERROR: The application fingerprint does not match this installer.
    goto :failed
)

if defined YT_DLP_GUI_VERIFY_ONLY (
    echo Package fingerprint verified.
    exit /b 0
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if errorlevel 1 goto :failed
copy /Y "%SOURCE_EXE%" "%INSTALLED_EXE%" >nul
if errorlevel 1 goto :failed
copy /Y "%SOURCE_UNINSTALLER%" "%INSTALL_DIR%\Uninstall-YT-DLP-GUI.bat" >nul
if errorlevel 1 goto :failed
copy /Y "%SOURCE_LICENSE%" "%INSTALL_DIR%\LICENSE" >nul
if errorlevel 1 goto :failed
copy /Y "%SOURCE_NOTICES%" "%INSTALL_DIR%\THIRD_PARTY_NOTICES.md" >nul
if errorlevel 1 goto :failed
"%POWERSHELL%" -NoLogo -NoProfile -NonInteractive -Command "$key='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\YT-DLP-GUI'; if (Test-Path -LiteralPath $key) { New-ItemProperty -Path $key -Name DisplayVersion -Value $env:APP_VERSION -PropertyType String -Force | Out-Null }"
if errorlevel 1 goto :failed

if not defined YT_DLP_GUI_NO_LAUNCH start "" "%INSTALLED_EXE%"
exit /b 0

:failed
echo.
echo No security settings were disabled or excluded.
if not defined YT_DLP_GUI_SILENT pause
exit /b 1
