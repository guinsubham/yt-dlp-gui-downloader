import ctypes
import os
import re
import shutil
# Required for the verified update handoff.
import subprocess  # nosec B404
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from networking import copy_stream_limited, download_verified_file, github_asset_details, read_json

RELEASE_API = "https://api.github.com/repos/guinsubham/yt-dlp-gui-downloader/releases/latest"
WINDOWS_ASSET_NAME = "YT-DLP-GUI-Windows.zip"
REQUIRED_ROOT_FILES = (
    "Install-YT-DLP-GUI.bat",
    "Install-YT-DLP-GUI.ps1",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "Uninstall-YT-DLP-GUI.bat",
    "Uninstall-YT-DLP-GUI.ps1",
    "YT-DLP-GUI.exe",
)
REQUIRED_LICENSE_FILES = (
    "brotli-LICENSE.txt",
    "certifi-LICENSE.txt",
    "charset-normalizer-LICENSE.txt",
    "idna-LICENSE.md",
    "Pillow-LICENSE.txt",
    "pycryptodomex-LICENSE.rst",
    "pyinstaller-COPYING.txt",
    "requests-LICENSE.txt",
    "requests-NOTICE.txt",
    "urllib3-LICENSE.txt",
    "websockets-LICENSE.txt",
    "yt-dlp-ejs-LICENSE.txt",
    "yt-dlp-UNLICENSE.txt",
)
REQUIRED_PACKAGE_FILES = REQUIRED_ROOT_FILES + tuple(
    f"third_party_licenses/{name}" for name in REQUIRED_LICENSE_FILES
)
MAX_ARCHIVE_SIZE = 512 * 1024 * 1024
MAX_MEMBER_SIZE = 300 * 1024 * 1024
MAX_EXTRACTED_SIZE = 600 * 1024 * 1024
INSTALLED_EXECUTABLE_PARTS = ("Programs", "YT-DLP-GUI", "YT-DLP-GUI.exe")
RUNNER_READY_TIMEOUT = 5.0


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    version: tuple[int, int, int]
    download_url: str
    sha256: str
    size: int


@dataclass(frozen=True)
class PreparedUpdate:
    release: ReleaseInfo
    temporary_directory: Path
    installer_path: Path


def parse_version(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", value.strip())
    if not match:
        raise ValueError(f"Unsupported release version: {value!r}")
    return tuple(int(part) for part in match.groups())


def get_latest_release() -> ReleaseInfo:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "YT-DLP-GUI-Updater",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    release = read_json(RELEASE_API, headers)

    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise RuntimeError("GitHub returned malformed release metadata.")
    asset = next(
        (
            item
            for item in assets
            if isinstance(item, dict) and item.get("name") == WINDOWS_ASSET_NAME
        ),
        None,
    )
    if asset is None:
        raise RuntimeError(f"The latest release does not contain {WINDOWS_ASSET_NAME}.")

    download_url, digest, size = github_asset_details(asset, maximum_size=MAX_ARCHIVE_SIZE)

    tag = str(release.get("tag_name", ""))
    return ReleaseInfo(
        tag=tag,
        version=parse_version(tag),
        download_url=download_url,
        sha256=digest,
        size=size,
    )


def prepare_update(release: ReleaseInfo, log, progress_callback=None) -> PreparedUpdate:
    temporary_directory = Path(tempfile.mkdtemp(prefix="YT-DLP-GUI-update-"))
    archive_path = temporary_directory / WINDOWS_ASSET_NAME
    package_directory = temporary_directory / "package"
    package_directory.mkdir()

    try:
        log(f"Downloading update {release.tag} from GitHub...")
        download_verified_file(
            release.download_url,
            archive_path,
            expected_sha256=release.sha256,
            expected_size=release.size,
            maximum_size=MAX_ARCHIVE_SIZE,
            headers={"User-Agent": "YT-DLP-GUI-Updater"},
            progress_callback=progress_callback,
        )

        log("Update checksum verified. Preparing installation...")
        with zipfile.ZipFile(archive_path) as archive:
            members_by_name = {}
            for member in archive.infolist():
                if member.is_dir():
                    continue
                member_path = PurePosixPath(member.filename.replace("\\", "/"))
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise RuntimeError("The update contains an unsafe archive path.")
                name = member_path.as_posix()
                if name in REQUIRED_PACKAGE_FILES:
                    if name in members_by_name:
                        raise RuntimeError(f"The update contains duplicate {name} files.")
                    members_by_name[name] = member

            missing = [name for name in REQUIRED_PACKAGE_FILES if name not in members_by_name]
            if missing:
                raise RuntimeError(f"The verified update is incomplete: {', '.join(missing)}.")

            extracted_size = sum(member.file_size for member in members_by_name.values())
            if extracted_size > MAX_EXTRACTED_SIZE:
                raise RuntimeError("The update exceeded the total extraction limit.")

            for name, member in members_by_name.items():
                destination_path = package_directory.joinpath(*PurePosixPath(name).parts)
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, destination_path.open("wb") as destination:
                    copy_stream_limited(
                        source,
                        destination,
                        expected_size=member.file_size,
                        maximum_size=MAX_MEMBER_SIZE,
                    )

        return PreparedUpdate(
            release=release,
            temporary_directory=temporary_directory,
            installer_path=package_directory / "Install-YT-DLP-GUI.bat",
        )
    except Exception:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        raise


def _powershell_literal(value: Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _windows_powershell_path() -> Path:
    if os.name != "nt":
        raise RuntimeError("Automatic update installation is supported on Windows only.")
    buffer = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(buffer, len(buffer))
    if length <= 0 or length >= len(buffer):
        raise RuntimeError("The Windows system directory could not be located.")
    executable = Path(buffer.value) / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    if not executable.is_file():
        raise RuntimeError("Windows PowerShell could not be located in the system directory.")
    return executable


def _installed_executable_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise RuntimeError("The current Windows user's application directory could not be located.")
    return Path(local_app_data).joinpath(*INSTALLED_EXECUTABLE_PARTS)


def _update_log_path() -> Path:
    return _installed_executable_path().parent / "update.log"


def _build_update_runner_script(
    update: PreparedUpdate,
    process_id: int,
    restart_executable: Path,
    installed_target: Path,
    log_path: Path,
    ready_path: Path,
) -> str:
    """Build the detached updater script without relying on fragile inline quoting."""
    lines = [
        "$ErrorActionPreference = 'Stop'",
        f"$processId = {int(process_id)}",
        f"$installerPath = {_powershell_literal(update.installer_path)}",
        f"$temporaryDirectory = {_powershell_literal(update.temporary_directory)}",
        f"$installedTarget = {_powershell_literal(installed_target)}",
        f"$fallbackTarget = {_powershell_literal(restart_executable)}",
        f"$logPath = {_powershell_literal(log_path)}",
        f"$readyPath = {_powershell_literal(ready_path)}",
        "$exitCode = 1",
        "$restartPath = $fallbackTarget",
        "",
        "function Write-UpdateLog {",
        "    param([string]$Message)",
        "    try {",
        "        $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'",
        "        Add-Content -LiteralPath $logPath -Value \"[$timestamp] $Message\" -Encoding UTF8",
        "    } catch {",
        "        # Diagnostics must never prevent installation or restart.",
        "    }",
        "}",
        "",
        "function Start-UpdatedApplication {",
        "    param([string]$ExecutablePath)",
        "    $workingDirectory = Split-Path -Parent $ExecutablePath",
        "    # The updater inherits the old one-file process state. Force the restarted",
        "    # executable to unpack into a fresh _MEI directory as an independent instance.",
        "    $env:PYINSTALLER_RESET_ENVIRONMENT = '1'",
        "    $launchedProcess = Start-Process -FilePath $ExecutablePath -WorkingDirectory $workingDirectory -PassThru",
        "    Start-Sleep -Seconds 2",
        "    if ($launchedProcess.HasExited) {",
        "        throw 'The application exited before restart completed.'",
        "    }",
        "    Write-UpdateLog \"Restarted application from $ExecutablePath (PID $($launchedProcess.Id)).\"",
        "}",
        "",
        "try {",
        "    New-Item -ItemType Directory -Path (Split-Path -Parent $logPath) -Force | Out-Null",
        "    Set-Content -LiteralPath $readyPath -Value $PID -Encoding ASCII",
        "    Write-UpdateLog \"Waiting for application process $processId to exit.\"",
        "    Wait-Process -Id $processId -ErrorAction SilentlyContinue",
        "    if (Test-Path -LiteralPath $fallbackTarget -PathType Leaf) {",
        "        Write-UpdateLog \"Waiting for the application executable to be released.\"",
        "        $releaseDeadline = (Get-Date).AddSeconds(30)",
        "        while ($true) {",
        "            try {",
        "                $lockProbe = [System.IO.File]::Open(",
        "                    $fallbackTarget,",
        "                    [System.IO.FileMode]::Open,",
        "                    [System.IO.FileAccess]::ReadWrite,",
        "                    [System.IO.FileShare]::None",
        "                )",
        "                $lockProbe.Dispose()",
        "                break",
        "            } catch [System.IO.IOException] {",
        "                if ((Get-Date) -ge $releaseDeadline) {",
        "                    throw 'The previous application process did not release its executable within 30 seconds.'",
        "                }",
        "                Start-Sleep -Milliseconds 200",
        "            } catch [System.UnauthorizedAccessException] {",
        "                if ((Get-Date) -ge $releaseDeadline) {",
        "                    throw 'The previous application executable remained unavailable for 30 seconds.'",
        "                }",
        "                Start-Sleep -Milliseconds 200",
        "            }",
        "        }",
        "        Write-UpdateLog 'The application executable was released.'",
        "    }",
        "    $env:YT_DLP_GUI_SILENT = '1'",
        "    $env:YT_DLP_GUI_NO_LAUNCH = '1'",
        "    Write-UpdateLog 'Starting verified package installer.'",
        "    & $installerPath",
        "    $installerExitCode = $LASTEXITCODE",
        "    if ($installerExitCode -ne 0) {",
        "        throw \"The package installer exited with code $installerExitCode.\"",
        "    }",
        "    if (Test-Path -LiteralPath $installedTarget -PathType Leaf) {",
        "        $restartPath = $installedTarget",
        "    } elseif (-not (Test-Path -LiteralPath $fallbackTarget -PathType Leaf)) {",
        "        throw 'No executable was available after installation.'",
        "    }",
        "    Start-UpdatedApplication $restartPath",
        "    $exitCode = 0",
        "} catch {",
        "    Write-UpdateLog \"Update failed: $($_.Exception.Message)\"",
        "    if (Test-Path -LiteralPath $fallbackTarget -PathType Leaf) {",
        "        try {",
        "            Start-UpdatedApplication $fallbackTarget",
        "        } catch {",
        "            Write-UpdateLog \"Fallback restart failed: $($_.Exception.Message)\"",
        "        }",
        "    }",
        "} finally {",
        "    Start-Sleep -Milliseconds 500",
        "    Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force -ErrorAction SilentlyContinue",
        "}",
        "exit $exitCode",
    ]
    return "\n".join(lines) + "\n"


def launch_update_after_exit(update: PreparedUpdate, process_id: int, restart_executable: Path) -> Path:
    installed_target = _installed_executable_path()
    log_path = _update_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    runner_path = update.temporary_directory / "Apply-YT-DLP-GUI-Update.ps1"
    ready_path = update.temporary_directory / "Apply-YT-DLP-GUI-Update.ready"
    ready_path.unlink(missing_ok=True)
    runner_path.write_text(
        _build_update_runner_script(
            update,
            process_id,
            restart_executable,
            installed_target,
            log_path,
            ready_path,
        ),
        encoding="utf-8-sig",
    )
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

    # Use the absolute system executable; no command search or shell expansion occurs.
    runner_process = subprocess.Popen(  # nosec B603
        [
            str(_windows_powershell_path()),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(runner_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation_flags,
    )

    deadline = time.monotonic() + RUNNER_READY_TIMEOUT
    while time.monotonic() < deadline:
        if ready_path.is_file():
            return log_path
        exit_code = runner_process.poll()
        if exit_code is not None:
            raise RuntimeError(f"The update helper exited before startup (code {exit_code}).")
        time.sleep(0.05)

    runner_process.terminate()
    raise RuntimeError("The update helper did not start within 5 seconds.")
