# YT-DLP GUI Downloader

A dark Windows desktop interface for downloading media with [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Features

- Video presets from 480p through the best available 4K format
- MP3 and M4A audio-only presets
- Eight concurrent fragment workers for supported downloads
- Live percentage, ETA, speed, file size, and activity output
- Automatic clipboard detection for copied YouTube links
- Bundled FFmpeg support in the Windows executable
- Dark Windows title bar and a responsive rounded interface

## Install on Windows

Install the latest release for your Windows user with one PowerShell command:

```powershell
irm https://raw.githubusercontent.com/guinsubham/yt-dlp-gui-downloader/main/install.ps1 | iex
```

The script downloads the latest GitHub release, verifies its published SHA-256 digest, runs the packaged installer, and removes its temporary files. It creates desktop and Start Menu shortcuts and registers a clean uninstaller without requesting administrator access or changing Windows security settings.

To review the installer before running it, download it first:

```powershell
irm https://raw.githubusercontent.com/guinsubham/yt-dlp-gui-downloader/main/install.ps1 -OutFile "$env:TEMP\install-ytdlp-gui.ps1"
notepad "$env:TEMP\install-ytdlp-gui.ps1"
& "$env:TEMP\install-ytdlp-gui.ps1"
```

Alternatively, download `YT-DLP-GUI-Windows.zip` from the latest GitHub Release, extract all three files, and run `Install-YT-DLP-GUI.bat`.

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

## Usage

Only download media you own or have permission to save. You are responsible for following the source website's terms and applicable law.
