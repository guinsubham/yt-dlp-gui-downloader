import importlib
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

MAX_THUMBNAIL_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 4
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class ThumbnailPreviewError(RuntimeError):
    pass


def best_thumbnail_url(info: dict | None) -> str | None:
    if not isinstance(info, dict):
        return None

    direct_url = info.get("thumbnail")
    if isinstance(direct_url, str) and direct_url.strip():
        return direct_url.strip()

    candidates = []
    for thumbnail in info.get("thumbnails") or []:
        if not isinstance(thumbnail, dict):
            continue
        url = thumbnail.get("url")
        if not isinstance(url, str) or not url.strip():
            continue
        width = thumbnail.get("width") or 0
        height = thumbnail.get("height") or 0
        try:
            area = int(width) * int(height)
        except (TypeError, ValueError):
            area = 0
        candidates.append((area, url.strip()))

    return max(candidates, default=(0, None))[1]


def display_media_title(info: dict | None, max_length: int = 110) -> str | None:
    if not isinstance(info, dict):
        return None

    raw_title = info.get("title") or info.get("fulltitle")
    if not isinstance(raw_title, str):
        return None

    normalized_title = " ".join(raw_title.split())
    if not normalized_title:
        return None

    max_length = max(4, int(max_length))
    if len(normalized_title) <= max_length:
        return normalized_title
    return normalized_title[: max_length - 3].rstrip() + "..."


def _validate_public_thumbnail_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 4096:
        raise ThumbnailPreviewError("The thumbnail URL is invalid.")

    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ThumbnailPreviewError("Thumbnail previews require a public HTTPS URL.")

    try:
        addresses = {
            result[4][0]
            for result in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as error:
        raise ThumbnailPreviewError("The thumbnail host could not be resolved.") from error

    if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
        raise ThumbnailPreviewError("The thumbnail host is not a public network address.")

    return url


def fetch_thumbnail_bytes(url: str, *, session=None) -> bytes:
    requests = importlib.import_module("requests")
    owns_session = session is None
    session = session or requests.Session()
    current_url = url

    try:
        for redirect_count in range(MAX_REDIRECTS + 1):
            _validate_public_thumbnail_url(current_url)
            response = session.get(
                current_url,
                allow_redirects=False,
                headers={"User-Agent": "YT-DLP-GUI-Thumbnail/1.0"},
                stream=True,
                timeout=(5, 10),
            )
            try:
                if response.status_code in REDIRECT_STATUSES:
                    location = response.headers.get("Location")
                    if not location or redirect_count == MAX_REDIRECTS:
                        raise ThumbnailPreviewError("The thumbnail redirected too many times.")
                    current_url = urljoin(current_url, location)
                    continue

                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type and not content_type.startswith("image/"):
                    raise ThumbnailPreviewError("The thumbnail response was not an image.")

                content_length = response.headers.get("Content-Length")
                if content_length:
                    try:
                        if int(content_length) > MAX_THUMBNAIL_BYTES:
                            raise ThumbnailPreviewError("The thumbnail exceeds the size limit.")
                    except ValueError:
                        pass

                payload = bytearray()
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    payload.extend(chunk)
                    if len(payload) > MAX_THUMBNAIL_BYTES:
                        raise ThumbnailPreviewError("The thumbnail exceeds the size limit.")
                if not payload:
                    raise ThumbnailPreviewError("The thumbnail response was empty.")
                return bytes(payload)
            finally:
                response.close()
    finally:
        if owns_session:
            session.close()

    raise ThumbnailPreviewError("The thumbnail could not be downloaded.")
