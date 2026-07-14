@echo off
setlocal EnableExtensions
title Install YT-DLP GUI Downloader

set "APP_NAME=YT-DLP GUI Downloader"
set "APP_VERSION=__APP_VERSION__"
set "SOURCE_EXE=%~dp0YT-DLP-GUI.exe"
set "SOURCE_UNINSTALLER=%~dp0Uninstall-YT-DLP-GUI.bat"
set "EXPECTED_HASH=__EXPECTED_HASH__"
set "INSTALL_DIR=%LOCALAPPDATA%\Programs\YT-DLP-GUI"
set "INSTALLED_EXE=%INSTALL_DIR%\YT-DLP-GUI.exe"
set "UNINSTALLER=%INSTALL_DIR%\Uninstall-YT-DLP-GUI.bat"
set "START_MENU_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\YT-DLP GUI Downloader"

echo Installing %APP_NAME%...
echo.

if not exist "%SOURCE_EXE%" (
    echo ERROR: YT-DLP-GUI.exe must be beside this installer.
    goto :failed
)

if not exist "%SOURCE_UNINSTALLER%" (
    echo ERROR: Uninstall-YT-DLP-GUI.bat must be beside this installer.
    goto :failed
)

for /f "usebackq delims=" %%H in (`powershell.exe -NoProfile -Command "(Get-FileHash -LiteralPath $env:SOURCE_EXE -Algorithm SHA256).Hash"`) do set "ACTUAL_HASH=%%H"
if not defined ACTUAL_HASH (
    echo ERROR: The application fingerprint could not be verified.
    goto :failed
)

if /I not "%ACTUAL_HASH%"=="%EXPECTED_HASH%" (
    echo ERROR: The application fingerprint does not match this installer.
    echo Expected: %EXPECTED_HASH%
    echo Actual:   %ACTUAL_HASH%
    echo Installation stopped without changing your computer.
    goto :failed
)

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
if errorlevel 1 goto :copy_failed

copy /Y "%SOURCE_EXE%" "%INSTALLED_EXE%" >nul
if errorlevel 1 goto :copy_failed
copy /Y "%SOURCE_UNINSTALLER%" "%UNINSTALLER%" >nul
if errorlevel 1 goto :copy_failed

if not exist "%START_MENU_DIR%" mkdir "%START_MENU_DIR%"

powershell.exe -NoProfile -Command "$shell=New-Object -ComObject WScript.Shell; function New-Link([string]$path,[string]$target){$link=$shell.CreateShortcut($path);$link.TargetPath=$target;$link.WorkingDirectory=$env:INSTALL_DIR;$link.IconLocation=$env:INSTALLED_EXE;$link.Save()}; $desktop=[Environment]::GetFolderPath('Desktop'); New-Link (Join-Path $desktop 'YT-DLP GUI Downloader.lnk') $env:INSTALLED_EXE; New-Link (Join-Path $env:START_MENU_DIR 'YT-DLP GUI Downloader.lnk') $env:INSTALLED_EXE; New-Link (Join-Path $env:START_MENU_DIR 'Uninstall YT-DLP GUI Downloader.lnk') $env:UNINSTALLER"
if errorlevel 1 goto :shortcut_failed

powershell.exe -NoProfile -Command "$key='HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\YT-DLP-GUI'; New-Item -Path $key -Force | Out-Null; New-ItemProperty -Path $key -Name DisplayName -Value 'YT-DLP GUI Downloader' -PropertyType String -Force | Out-Null; New-ItemProperty -Path $key -Name DisplayVersion -Value $env:APP_VERSION -PropertyType String -Force | Out-Null; New-ItemProperty -Path $key -Name DisplayIcon -Value $env:INSTALLED_EXE -PropertyType String -Force | Out-Null; New-ItemProperty -Path $key -Name InstallLocation -Value $env:INSTALL_DIR -PropertyType String -Force | Out-Null; New-ItemProperty -Path $key -Name UninstallString -Value ('"' + $env:UNINSTALLER + '"') -PropertyType String -Force | Out-Null; New-ItemProperty -Path $key -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null; New-ItemProperty -Path $key -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null"
if errorlevel 1 goto :registry_failed

echo.
echo %APP_NAME% was installed successfully.
start "" "%INSTALLED_EXE%"
exit /b 0

:copy_failed
echo ERROR: The application files could not be installed.
goto :failed

:shortcut_failed
echo ERROR: Windows could not create the application shortcuts.
goto :failed

:registry_failed
echo ERROR: Windows could not register the uninstaller.
goto :failed

:failed
echo.
echo No security settings were disabled or excluded.
pause
exit /b 1
