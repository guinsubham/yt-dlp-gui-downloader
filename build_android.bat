@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
if not defined JAVA_HOME (
    echo JAVA_HOME is not set. Install JDK 17 and set JAVA_HOME first.
    exit /b 1
)

if not defined ANDROID_HOME set "ANDROID_HOME=%ANDROID_SDK_ROOT%"
if not defined ANDROID_HOME (
    echo ANDROID_HOME or ANDROID_SDK_ROOT must point to an Android SDK installation.
    exit /b 1
)
set "ANDROID_SDK_ROOT=%ANDROID_HOME%"

set "GRADLE=%ROOT%tools\gradle-8.10.2\bin\gradle.bat"
if exist "%GRADLE%" goto build

where gradle.bat >nul 2>nul
if errorlevel 1 (
    echo Gradle 8.10.2 was not found in tools or on PATH.
    exit /b 1
)
set "GRADLE=gradle.bat"

:build
call "%GRADLE%" -p "%ROOT%android_app" assembleDebug
if errorlevel 1 exit /b %errorlevel%

if not exist "%ROOT%dist" mkdir "%ROOT%dist"
copy /Y "%ROOT%android_app\app\build\outputs\apk\debug\app-debug.apk" "%ROOT%dist\YT-DLP-GUI-Android-debug.apk" >nul
echo Android APK built:
echo %ROOT%dist\YT-DLP-GUI-Android-debug.apk
