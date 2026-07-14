import os
import re
import shutil
# Required for fixed-argument executable version checks.
import subprocess  # nosec B404
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from networking import copy_stream_limited, download_verified_file, github_asset_details, read_json


USER_AGENT = "YT-DLP-GUI-Dependency-Installer"
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": USER_AGENT,
    "X-GitHub-Api-Version": "2022-11-28",
}

DENO_RELEASE_API = "https://api.github.com/repos/denoland/deno/releases/latest"
DENO_WINDOWS_ASSET = "deno-x86_64-pc-windows-msvc.zip"
DENO_MAX_ARCHIVE_SIZE = 100 * 1024 * 1024
DENO_MAX_EXECUTABLE_SIZE = 200 * 1024 * 1024
MINIMUM_DENO_VERSION = (2, 6, 6)

FFMPEG_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
FFMPEG_WINDOWS_ASSET = "ffmpeg-master-latest-win64-lgpl.zip"
FFMPEG_MAX_ARCHIVE_SIZE = 300 * 1024 * 1024
FFMPEG_MAX_EXECUTABLE_SIZE = 250 * 1024 * 1024


def _runtime_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Programs" / "YT-DLP-GUI" / "runtime"
    return Path.home() / ".yt-dlp-gui" / "runtime"


def _creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _run_version(executable: Path, *arguments: str) -> str | None:
    if not executable.is_file():
        return None
    try:
        # The executable is verified before use and arguments are fixed by the caller.
        result = subprocess.run(  # nosec B603
            [str(executable), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=15,
            check=False,
            creationflags=_creation_flags(),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _deno_version(executable: Path) -> tuple[int, int, int] | None:
    output = _run_version(executable, "--version")
    match = re.search(r"^deno\s+(\d+)\.(\d+)\.(\d+)", output or "", re.MULTILINE)
    return tuple(int(part) for part in match.groups()) if match else None


def _ffmpeg_is_ready(executable: Path) -> bool:
    output = _run_version(executable, "-version")
    return bool(re.search(r"^ffmpeg version\s+\S+", output or "", re.MULTILINE))


def _find_release_asset(api_url: str, asset_name: str, maximum_size: int) -> tuple[str, str, int, str]:
    release = read_json(api_url, GITHUB_HEADERS)
    assets = release.get("assets", [])
    if not isinstance(assets, list):
        raise RuntimeError("GitHub returned malformed release metadata.")
    asset = next(
        (item for item in assets if isinstance(item, dict) and item.get("name") == asset_name),
        None,
    )
    if asset is None:
        raise RuntimeError(f"The latest release does not contain {asset_name}.")
    url, digest, size = github_asset_details(asset, maximum_size=maximum_size)
    return url, digest, size, str(release.get("tag_name", "latest"))


def _download_asset(api_url: str, asset_name: str, maximum_size: int, archive_path: Path, log) -> None:
    url, digest, size, tag = _find_release_asset(api_url, asset_name, maximum_size)
    log(f"Downloading {asset_name} ({tag}) from its official GitHub release...")
    download_verified_file(
        url,
        archive_path,
        expected_sha256=digest,
        expected_size=size,
        maximum_size=maximum_size,
        headers=GITHUB_HEADERS,
    )


def _single_archive_member(archive: zipfile.ZipFile, filename: str) -> zipfile.ZipInfo:
    matches = [
        member
        for member in archive.infolist()
        if not member.is_dir() and PurePosixPath(member.filename).name.lower() == filename.lower()
    ]
    if len(matches) != 1:
        raise RuntimeError(f"The verified archive does not contain exactly one {filename} file.")
    return matches[0]


def _extract_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo, destination: Path) -> None:
    with archive.open(member) as source, destination.open("wb") as output:
        copy_stream_limited(
            source,
            output,
            expected_size=member.file_size,
            maximum_size=FFMPEG_MAX_EXECUTABLE_SIZE,
        )


def _download_deno_runtime(target: Path, log) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("Automatic Deno installation is currently supported on Windows only.")

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="YT-DLP-GUI-deno-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        archive_path = temporary_path / DENO_WINDOWS_ASSET
        staged_executable = temporary_path / "deno.exe"
        _download_asset(DENO_RELEASE_API, DENO_WINDOWS_ASSET, DENO_MAX_ARCHIVE_SIZE, archive_path, log)

        with zipfile.ZipFile(archive_path) as archive:
            member = _single_archive_member(archive, "deno.exe")
            with archive.open(member) as source, staged_executable.open("wb") as output:
                copy_stream_limited(
                    source,
                    output,
                    expected_size=member.file_size,
                    maximum_size=DENO_MAX_EXECUTABLE_SIZE,
                )

        version = _deno_version(staged_executable)
        if version is None or version < MINIMUM_DENO_VERSION:
            raise RuntimeError("The downloaded Deno executable did not pass its version check.")
        os.replace(staged_executable, target)

    log(f"Deno {'.'.join(map(str, version))} installed and verified.")
    return target


def ensure_deno_runtime(log, runtime_directory: Path | None = None) -> Path:
    """Use the managed Deno executable, or securely install one for this app."""
    managed_path = (runtime_directory / "deno.exe") if runtime_directory else (_runtime_root() / "deno.exe")
    version = _deno_version(managed_path)
    if version is not None and version >= MINIMUM_DENO_VERSION:
        log(f"Deno {'.'.join(map(str, version))} ready.")
        return managed_path

    log("The script runtime is not installed. Starting verified first-run setup...")
    return _download_deno_runtime(managed_path, log)


def _download_ffmpeg_runtime(target_directory: Path, log) -> Path:
    if sys.platform != "win32":
        raise RuntimeError("Automatic media processor installation is currently supported on Windows only.")

    target_directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="YT-DLP-GUI-ffmpeg-") as temporary_directory:
        temporary_path = Path(temporary_directory)
        archive_path = temporary_path / FFMPEG_WINDOWS_ASSET
        staged_directory = temporary_path / "ffmpeg"
        staged_directory.mkdir()
        _download_asset(FFMPEG_RELEASE_API, FFMPEG_WINDOWS_ASSET, FFMPEG_MAX_ARCHIVE_SIZE, archive_path, log)

        with zipfile.ZipFile(archive_path) as archive:
            for filename in ("ffmpeg.exe", "ffprobe.exe"):
                _extract_member(archive, _single_archive_member(archive, filename), staged_directory / filename)
            _extract_member(
                archive,
                _single_archive_member(archive, "LICENSE.txt"),
                staged_directory / "FFMPEG-LICENSE.txt",
            )

        staged_executable = staged_directory / "ffmpeg.exe"
        if not _ffmpeg_is_ready(staged_executable):
            raise RuntimeError("The downloaded media processor did not pass its version check.")

        if target_directory.exists():
            shutil.rmtree(target_directory)
        os.replace(staged_directory, target_directory)

    log("The media processor was installed and verified.")
    return target_directory / "ffmpeg.exe"


def ensure_ffmpeg_runtime(log, runtime_directory: Path | None = None) -> Path:
    """Use a complete processor installation, or securely install the LGPL build."""
    target_directory = (runtime_directory / "ffmpeg") if runtime_directory else (_runtime_root() / "ffmpeg")
    managed_executable = target_directory / "ffmpeg.exe"
    managed_probe = target_directory / "ffprobe.exe"
    managed_license = target_directory / "FFMPEG-LICENSE.txt"
    if _ffmpeg_is_ready(managed_executable) and managed_probe.is_file() and managed_license.is_file():
        log("The media processor is ready.")
        return managed_executable

    log("The media processor is not installed. Starting verified first-run setup...")
    return _download_ffmpeg_runtime(target_directory, log)
