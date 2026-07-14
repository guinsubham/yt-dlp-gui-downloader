# YT-DLP GUI Downloader

A dark Windows desktop interface for downloading media with [yt-dlp](https://github.com/yt-dlp/yt-dlp). The repository also contains an experimental native Android build.

## Features

- Video presets from 480p through the best available 4K format
- MP3 and M4A audio-only presets
- Eight concurrent fragment workers for supported downloads
- Live percentage, ETA, speed, file size, and activity output
- Automatic clipboard detection for copied YouTube links
- Bundled FFmpeg support in the Windows executable
- Dark Windows title bar and a responsive rounded interface

## Install on Windows

Download `YT-DLP-GUI-Windows.zip` from the latest GitHub Release, extract all three files, and run `Install-YT-DLP-GUI.bat`.

The installer verifies the executable's SHA-256 fingerprint, installs for the current user, creates desktop and Start Menu shortcuts, and registers a clean uninstaller. It does not disable or modify Windows security settings.

The current Windows executable is unsigned, so Microsoft SmartScreen may identify it as an unrecognized application.

## Build the Windows app

Requirements:

- Windows 10 or Windows 11
- Python 3.10 or newer

Run:

```bat
build_exe.bat
```

The standalone executable is written to `dist\YT-DLP-GUI.exe`.

## Android build

The Android project lives in `android_app`. It requires JDK 17, Android SDK 35, and Gradle 8.10.2 or a compatible Gradle installation.

Set `JAVA_HOME` and either `ANDROID_HOME` or `ANDROID_SDK_ROOT`, then run:

```bat
build_android.bat
```

The Android build is experimental. FFmpeg-dependent merging may require additional Android FFmpeg support.

## Usage

Only download media you own or have permission to save. You are responsible for following the source website's terms and applicable law.
