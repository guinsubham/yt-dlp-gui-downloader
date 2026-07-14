import ctypes
import os
import re
import shutil
# Required for the verified update handoff.
import subprocess  # nosec B404
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from networking import copy_stream_limited, download_verified_file, github_asset_details, read_json

RELEASE_API = "https://api.github.com/repos/guinsubham/yt-dlp-gui-downloader/releases/latest"
WINDOWS_ASSET_NAME = "YT-DLP-GUI-Windows.zip"
REQUIRED_PACKAGE_FILES = (
    "Install-YT-DLP-GUI.bat",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "Uninstall-YT-DLP-GUI.bat",
    "YT-DLP-GUI.exe",
)
MAX_ARCHIVE_SIZE = 512 * 1024 * 1024
MAX_MEMBER_SIZE = 300 * 1024 * 1024
MAX_EXTRACTED_SIZE = 600 * 1024 * 1024


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

    asset = next(
        (item for item in release.get("assets", []) if item.get("name") == WINDOWS_ASSET_NAME),
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


def prepare_update(release: ReleaseInfo, log) -> PreparedUpdate:
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
        )

        log("Update checksum verified. Preparing installation...")
        with zipfile.ZipFile(archive_path) as archive:
            members_by_name = {}
            for member in archive.infolist():
                if member.is_dir():
                    continue
                name = PurePosixPath(member.filename).name
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
                destination_path = package_directory / name
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


def launch_update_after_exit(update: PreparedUpdate, process_id: int, restart_executable: Path) -> None:
    installer = _powershell_literal(update.installer_path)
    temporary_directory = _powershell_literal(update.temporary_directory)
    restart_target = _powershell_literal(restart_executable)
    command = (
        "$ErrorActionPreference='Stop';"
        f"Wait-Process -Id {int(process_id)} -ErrorAction SilentlyContinue;"
        "$env:YT_DLP_GUI_SILENT='1';"
        "$exitCode=1;"
        f"try {{ & {installer}; $exitCode=$LASTEXITCODE }} finally {{ "
        "Start-Sleep -Seconds 3;"
        f"Remove-Item -LiteralPath {temporary_directory} -Recurse -Force -ErrorAction SilentlyContinue }};"
        f"if ($exitCode -ne 0) {{ Start-Process -FilePath {restart_target} }};"
        "exit $exitCode"
    )
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS

    # Use the absolute system executable; no command search or shell expansion occurs.
    subprocess.Popen(  # nosec B603
        [
            str(_windows_powershell_path()),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            command,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation_flags,
    )
