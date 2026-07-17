import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


GITHUB_DOWNLOAD_HOSTS = frozenset({
    "github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
})
GITHUB_API_HOSTS = frozenset({"api.github.com"})
MAX_JSON_SIZE = 2 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def require_https_url(url: str, allowed_hosts: frozenset[str]) -> str:
    """Reject unexpected schemes and hosts before opening a remote resource."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in allowed_hosts or parsed.username or parsed.password:
        raise RuntimeError("The remote address did not pass the security policy.")
    return url


def _validate_final_url(response, allowed_hosts: frozenset[str]) -> None:
    get_url = getattr(response, "geturl", None)
    if get_url:
        require_https_url(str(get_url()), allowed_hosts)


class _AllowlistedRedirectHandler(HTTPRedirectHandler):
    """Validate every redirect before urllib opens the next connection."""

    def __init__(self, allowed_hosts: frozenset[str]):
        self.allowed_hosts = allowed_hosts

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        require_https_url(new_url, self.allowed_hosts)
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def _open_allowlisted(request: Request, allowed_hosts: frozenset[str], timeout: int):
    opener = build_opener(_AllowlistedRedirectHandler(allowed_hosts))
    return opener.open(request, timeout=timeout)


def read_json(url: str, headers: dict[str, str], *, timeout: int = 30) -> dict:
    require_https_url(url, GITHUB_API_HOSTS)
    request = Request(url, headers=headers)
    with _open_allowlisted(request, GITHUB_API_HOSTS, timeout) as response:
        _validate_final_url(response, GITHUB_API_HOSTS)
        payload = response.read(MAX_JSON_SIZE + 1)

    if len(payload) > MAX_JSON_SIZE:
        raise RuntimeError("The remote metadata response was unexpectedly large.")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("The remote metadata response was not valid JSON.") from error
    if not isinstance(decoded, dict):
        raise RuntimeError("The remote metadata response had an unexpected shape.")
    return decoded


def github_asset_details(asset: dict, *, maximum_size: int) -> tuple[str, str, int]:
    """Validate the URL, checksum, and size supplied by GitHub for an asset."""
    digest_match = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", str(asset.get("digest", "")))
    if not digest_match:
        raise RuntimeError("GitHub did not provide a valid SHA-256 digest for the file.")

    try:
        size = int(asset.get("size", 0))
    except (TypeError, ValueError) as error:
        raise RuntimeError("GitHub reported an invalid file size.") from error
    if size <= 0 or size > maximum_size:
        raise RuntimeError("GitHub reported an invalid file size.")

    url = require_https_url(str(asset.get("browser_download_url", "")), GITHUB_DOWNLOAD_HOSTS)
    return url, digest_match.group(1).lower(), size


def download_verified_file(
    url: str,
    destination: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    maximum_size: int,
    headers: dict[str, str],
    timeout: int = 120,
    progress_callback=None,
) -> None:
    """Download one allowlisted GitHub asset and verify its exact size and digest."""
    require_https_url(url, GITHUB_DOWNLOAD_HOSTS)
    request = Request(url, headers=headers)
    hasher = hashlib.sha256()
    downloaded_size = 0
    if progress_callback:
        progress_callback(0, expected_size)

    with _open_allowlisted(request, GITHUB_DOWNLOAD_HOSTS, timeout) as response, destination.open("wb") as output:
        _validate_final_url(response, GITHUB_DOWNLOAD_HOSTS)
        while chunk := response.read(CHUNK_SIZE):
            downloaded_size += len(chunk)
            if downloaded_size > maximum_size or downloaded_size > expected_size:
                raise RuntimeError("The downloaded file exceeded its verified size.")
            output.write(chunk)
            hasher.update(chunk)
            if progress_callback:
                progress_callback(downloaded_size, expected_size)

    if downloaded_size != expected_size:
        raise RuntimeError("The downloaded file size did not match GitHub metadata.")
    if hasher.hexdigest().lower() != expected_sha256.lower():
        raise RuntimeError("The downloaded file failed SHA-256 verification.")


def copy_stream_limited(source, destination, *, expected_size: int, maximum_size: int) -> None:
    """Copy an archive member without trusting its declared uncompressed size."""
    if expected_size < 0 or expected_size > maximum_size:
        raise RuntimeError("An archive member exceeded the extraction limit.")

    copied = 0
    while chunk := source.read(CHUNK_SIZE):
        copied += len(chunk)
        if copied > expected_size or copied > maximum_size:
            raise RuntimeError("An archive member exceeded the extraction limit.")
        destination.write(chunk)
    if copied != expected_size:
        raise RuntimeError("An archive member size did not match its metadata.")
