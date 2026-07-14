import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

RELEASE_API = "https://api.github.com/repos/guinsubham/yt-dlp-gui-downloader/releases/latest"
WINDOWS_ASSET_NAME = "YT-DLP-GUI-Windows.zip"
REQUIRED_PACKAGE_FILES = (
    "Install-YT-DLP-GUI.bat",
    "Uninstall-YT-DLP-GUI.bat",
    "YT-DLP-GUI.exe",
)
MAX_ARCHIVE_SIZE = 512 * 1024 * 1024


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
    with urlopen(Request(RELEASE_API, headers=headers), timeout=30) as response:
        release = json.load(response)

    asset = next(
        (item for item in release.get("assets", []) if item.get("name") == WINDOWS_ASSET_NAME),
        None,
    )
    if asset is None:
        raise RuntimeError(f"The latest release does not contain {WINDOWS_ASSET_NAME}.")

    digest_match = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", str(asset.get("digest", "")))
    if not digest_match:
        raise RuntimeError("GitHub did not provide a valid SHA-256 digest for the update.")

    size = int(asset.get("size", 0))
    if size <= 0 or size > MAX_ARCHIVE_SIZE:
        raise RuntimeError("GitHub reported an invalid update package size.")

    tag = str(release.get("tag_name", ""))
    return ReleaseInfo(
        tag=tag,
        version=parse_version(tag),
        download_url=str(asset["browser_download_url"]),
        sha256=digest_match.group(1).lower(),
        size=size,
    )


def prepare_update(release: ReleaseInfo, log) -> PreparedUpdate:
    temporary_directory = Path(tempfile.mkdtemp(prefix="YT-DLP-GUI-update-"))
    archive_path = temporary_directory / WINDOWS_ASSET_NAME
    package_directory = temporary_directory / "package"
    package_directory.mkdir()

    try:
        headers = {"User-Agent": "YT-DLP-GUI-Updater"}
        request = Request(release.download_url, headers=headers)
        hasher = hashlib.sha256()
        downloaded_size = 0

        log(f"Downloading update {release.tag} from GitHub...")
        with urlopen(request, timeout=120) as response, archive_path.open("wb") as destination:
            while chunk := response.read(1024 * 1024):
                downloaded_size += len(chunk)
                if downloaded_size > MAX_ARCHIVE_SIZE:
                    raise RuntimeError("The update package exceeded the allowed size.")
                destination.write(chunk)
                hasher.update(chunk)

        if downloaded_size != release.size:
            raise RuntimeError("The downloaded update size does not match GitHub metadata.")
        if hasher.hexdigest().lower() != release.sha256:
            raise RuntimeError("The downloaded update failed SHA-256 verification.")

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

            for name, member in members_by_name.items():
                destination_path = package_directory / name
                with archive.open(member) as source, destination_path.open("wb") as destination:
                    shutil.copyfileobj(source, destination)

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

    subprocess.Popen(
        [
            "powershell.exe",
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
