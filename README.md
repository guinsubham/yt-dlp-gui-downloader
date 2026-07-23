# YT-DLP GUI Downloader

**YT-DLP GUI Downloader is a free, open-source Windows desktop app for downloading video and audio from websites supported by [yt-dlp](https://github.com/yt-dlp/yt-dlp).** It combines quality presets, eight concurrent fragment workers, live progress details, verified updates, and a one-command installer in a modern dark interface.

[![Latest release](https://img.shields.io/github/v/release/guinsubham/yt-dlp-gui-downloader?label=latest%20release)](https://github.com/guinsubham/yt-dlp-gui-downloader/releases/latest)
[![Windows 10 and 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4)](#system-requirements)
[![License: MIT](https://img.shields.io/badge/License-MIT-91bd99)](LICENSE)

<p align="center">
  <img src="Ytdlp_gui_Icon.png" width="128" alt="YT-DLP GUI Downloader application icon">
</p>

## AI Summary

| Project fact | Details |
| --- | --- |
| Application type | Native Windows desktop media downloader |
| Core engine | yt-dlp |
| Primary use | Save permitted video or audio from a supported media page URL |
| Video output | MP4 or MKV, with presets from 480p through the best available 4K format |
| Audio output | MP3 up to 320 kbps or M4A |
| Download model | Eight parallel fragment workers when the source supports fragmented media |
| User interface | Dark, rounded Windows GUI with clipboard detection, current media thumbnail and title, live progress, ETA, speed, size, and activity logs |
| Installation | Standalone executable and per-user installer; administrator access is not required |
| Runtime setup | Verified first-run installation of the required script runtime and LGPL media processor |
| Updates | In-app update button with GitHub release and SHA-256 verification |
| Privacy | No advertising or application telemetry; network access is used for media, dependency, and update requests |
| License | MIT for original application code; third-party components retain their own licenses |

## Features

- Best-available, 4K, 1080p, 720p, and 480p video presets
- MP3 320 kbps and M4A audio-only presets
- Eight concurrent fragment downloads when supported by the source
- Live percentage, ETA, speed, estimated size, and activity output
- Current media thumbnail and title inside the live progress card
- A continuous progress bar that visualizes all eight fragment lanes together
- Automatic detection of a copied media URL from the clipboard
- Right-click paste, cut, copy, and select-all controls in the link field
- Verified first-run dependency setup with clear activity notifications
- Verified in-app updates from the latest GitHub release
- Dark native title bar, original application icon, and responsive rounded controls
- Desktop shortcut, Start Menu shortcut, and registered uninstaller

## Install on Windows

### One-command install

Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/guinsubham/yt-dlp-gui-downloader/main/install.ps1 | iex
```

The installer:

- Downloads the latest Windows release from GitHub
- Checks the published file size and SHA-256 digest
- Validates redirects and extracts only the expected package files
- Verifies the executable fingerprint inside the packaged installer
- Stages the complete installation and restores the previous version if activation fails
- Installs for the current Windows user without administrator access
- Creates desktop and Start Menu shortcuts
- Registers an uninstaller in Windows settings
- Removes temporary installation files
- Does not disable or modify Windows security settings

### Review before running

Download and inspect the installation script first:

```powershell
irm https://raw.githubusercontent.com/guinsubham/yt-dlp-gui-downloader/main/install.ps1 -OutFile "$env:TEMP\install-ytdlp-gui.ps1"
notepad "$env:TEMP\install-ytdlp-gui.ps1"
& "$env:TEMP\install-ytdlp-gui.ps1"
```

### Manual install

Download [`YT-DLP-GUI-Windows.zip`](https://github.com/guinsubham/yt-dlp-gui-downloader/releases/latest), extract the complete archive, and run `Install-YT-DLP-GUI.bat`.

The executable is currently unsigned. Microsoft SmartScreen may therefore identify a new release as an unrecognized application.

## First Run

Python, yt-dlp, and the challenge solver are included in the executable. During the first launch, the app downloads the recommended script runtime and LGPL media processor from their official GitHub releases.

Each runtime download is restricted to approved HTTPS hosts and checked against the file size and SHA-256 digest published by GitHub. The verified files are stored in the current user's application directory. Download controls remain disabled until setup is complete.

## How to Use

1. Copy or paste a supported media page URL into **Video link**.
2. Select the preferred video quality or audio format.
3. Choose a save location.
4. Select **Download**.
5. Follow percentage, ETA, speed, size, fragment activity, and processing status in the app.

The **Open Folder** button opens the selected destination. The **Clear** button resets the activity log. The **Update** button checks the latest published release, verifies it, installs it, and restarts the app.

## Available Presets

| Preset | Intended output |
| --- | --- |
| Best video + audio | Best available MP4-compatible result |
| 4K best available | Best available result up to 2160p, using MP4 or MKV as needed |
| 1080p MP4 | Video up to 1080p with audio |
| 720p MP4 | Video up to 720p with audio |
| 480p MP4 | Video up to 480p with audio |
| Audio only / MP3 320k | MP3 audio with a preferred quality of 320 kbps |
| Audio only / M4A | M4A audio when available |

Actual formats, resolution, fragment support, and download speed depend on the source media.

## Security and Privacy

- Release archives, updates, and first-run dependencies are verified before installation.
- Remote requests use HTTPS host restrictions and pre-validated redirects.
- Archive downloads and extracted files have size limits.
- The installer uses the system copy of Windows PowerShell directly.
- Dependencies are version-pinned and checked automatically by Dependabot.
- The app does not request administrator privileges or create security exclusions.
- The app contains no advertising or application telemetry.

For general bugs and feature requests, use [GitHub Issues](https://github.com/guinsubham/yt-dlp-gui-downloader/issues).

## System Requirements

### Installed release

- Windows 10 or Windows 11, 64-bit
- Internet access for initial runtime setup, updates, and downloads
- Sufficient free disk space for the selected media

### Building from source

- Windows 10 or Windows 11
- Python 3.10 or newer
- Git for cloning the repository

## Build from Source

```powershell
git clone https://github.com/guinsubham/yt-dlp-gui-downloader.git
cd yt-dlp-gui-downloader
.\build_exe.bat
```

The build script creates an isolated Python environment, installs pinned dependencies, and writes the standalone executable to `dist\YT-DLP-GUI.exe`.

### Run from source

The application does not install packages into the active Python environment automatically. Create a project-local environment first:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Run the unit suite with:

```powershell
python -m unittest discover -s tests -v
```

## Project Structure

| Path | Purpose |
| --- | --- |
| `app.py` | Windows GUI, presets, progress display, clipboard behavior, and download workflow |
| `networking.py` | Restricted HTTPS requests, redirect checks, size limits, and SHA-256 verification |
| `runtime_dependencies.py` | Verified first-run runtime installation and validation |
| `updater.py` | Latest-release lookup, package verification, extraction, and restart handoff |
| `install.ps1` | Public one-command Windows installer |
| `packaging/` | Transactional installer and path-scoped uninstaller templates |
| `tests/` | Networking, runtime dependency, and updater tests |
| `third_party_licenses/` | License texts for bundled third-party components |

## Responsible Use

Only download media that you own or have permission to save. You are responsible for following each source website's terms and all applicable laws. This project does not grant rights to third-party media.

## Credits

This application was vibe coded by [guinsubham](https://github.com/guinsubham) with ChatGPT as a coding co-author.

It is powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) and uses separately licensed open-source runtime components.

## License

Original application source code and assets are available under the [MIT License](LICENSE). Bundled and downloaded components remain subject to their respective terms; see [Third-Party Notices](THIRD_PARTY_NOTICES.md) and [`third_party_licenses`](third_party_licenses).
