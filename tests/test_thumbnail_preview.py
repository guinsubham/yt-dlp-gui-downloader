import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import thumbnail_preview


class FakeResponse:
    def __init__(self, chunks, headers=None, status_code=200):
        self.chunks = chunks
        self.headers = headers or {"Content-Type": "image/jpeg"}
        self.status_code = status_code

    def iter_content(self, chunk_size):
        del chunk_size
        yield from self.chunks

    def raise_for_status(self):
        return None

    def close(self):
        return None


class FakeSession:
    def __init__(self, response):
        self.response = response

    def get(self, *_args, **_kwargs):
        return self.response


class ThumbnailPreviewTests(unittest.TestCase):
    def test_best_thumbnail_url_prefers_direct_url(self):
        info = {
            "thumbnail": "https://cdn.example/primary.jpg",
            "thumbnails": [{"url": "https://cdn.example/fallback.jpg", "width": 1920, "height": 1080}],
        }
        self.assertEqual(thumbnail_preview.best_thumbnail_url(info), info["thumbnail"])

    def test_best_thumbnail_url_uses_largest_fallback(self):
        info = {
            "thumbnails": [
                {"url": "https://cdn.example/small.jpg", "width": 320, "height": 180},
                {"url": "https://cdn.example/large.jpg", "width": 1280, "height": 720},
            ]
        }
        self.assertEqual(
            thumbnail_preview.best_thumbnail_url(info),
            "https://cdn.example/large.jpg",
        )

    def test_display_media_title_normalizes_and_shortens_text(self):
        info = {"title": "  A title\nwith   irregular spacing that is too long  "}
        self.assertEqual(
            thumbnail_preview.display_media_title(info, max_length=30),
            "A title with irregular spac...",
        )

    def test_display_media_title_ignores_missing_title(self):
        self.assertIsNone(thumbnail_preview.display_media_title({"id": "example"}))

    def test_cached_thumbnail_path_is_stable_and_cache_can_be_cleared(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_directory = Path(temporary_directory) / "thumbnails"
            first_path = thumbnail_preview.cached_thumbnail_path(
                cache_directory,
                "https://cdn.example/image.jpg",
            )
            second_path = thumbnail_preview.cached_thumbnail_path(
                cache_directory,
                "https://cdn.example/image.jpg",
            )
            self.assertEqual(first_path, second_path)
            self.assertEqual(first_path.suffix, ".png")

            cache_directory.mkdir()
            first_path.write_bytes(b"cached thumbnail")
            thumbnail_preview.clear_thumbnail_cache(cache_directory)
            self.assertFalse(cache_directory.exists())

    def test_thumbnail_url_rejects_private_network_hosts(self):
        private_result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        with patch("thumbnail_preview.socket.getaddrinfo", return_value=private_result):
            with self.assertRaisesRegex(thumbnail_preview.ThumbnailPreviewError, "public network"):
                thumbnail_preview._validate_public_thumbnail_url("https://example.test/image.jpg")

    def test_fetch_thumbnail_bytes_enforces_streaming_size_limit(self):
        response = FakeResponse([b"x" * (thumbnail_preview.MAX_THUMBNAIL_BYTES + 1)])
        session = FakeSession(response)
        public_result = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        with patch("thumbnail_preview.socket.getaddrinfo", return_value=public_result):
            with self.assertRaisesRegex(thumbnail_preview.ThumbnailPreviewError, "size limit"):
                thumbnail_preview.fetch_thumbnail_bytes(
                    "https://example.test/image.jpg",
                    session=session,
                )


if __name__ == "__main__":
    unittest.main()
