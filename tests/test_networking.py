import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import networking


class NetworkingTests(unittest.TestCase):
    def test_require_https_url_rejects_insecure_or_unexpected_hosts(self):
        with self.assertRaises(RuntimeError):
            networking.require_https_url("http://github.com/file.zip", networking.GITHUB_DOWNLOAD_HOSTS)
        with self.assertRaises(RuntimeError):
            networking.require_https_url("https://example.test/file.zip", networking.GITHUB_DOWNLOAD_HOSTS)

    def test_read_json_rejects_non_object_payload(self):
        with patch("networking._open_allowlisted", return_value=io.BytesIO(json.dumps([]).encode())):
            with self.assertRaisesRegex(RuntimeError, "unexpected shape"):
                networking.read_json("https://api.github.com/example", {})

    def test_redirect_handler_rejects_an_unexpected_host_before_following(self):
        handler = networking._AllowlistedRedirectHandler(networking.GITHUB_DOWNLOAD_HOSTS)
        request = networking.Request("https://github.com/example/file")
        with self.assertRaises(RuntimeError):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://example.test/untrusted-file",
            )

    def test_download_verified_file_enforces_exact_size_and_digest(self):
        payload = b"verified payload"
        progress = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "asset.bin"
            with patch("networking._open_allowlisted", return_value=io.BytesIO(payload)):
                networking.download_verified_file(
                    "https://github.com/example/project/releases/download/v1/asset.bin",
                    destination,
                    expected_sha256=hashlib.sha256(payload).hexdigest(),
                    expected_size=len(payload),
                    maximum_size=1024,
                    headers={},
                    progress_callback=lambda downloaded, total: progress.append((downloaded, total)),
                )
            self.assertEqual(destination.read_bytes(), payload)
        self.assertEqual(progress, [(0, len(payload)), (len(payload), len(payload))])

    def test_download_verified_file_rejects_size_mismatch(self):
        payload = b"too short"
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "asset.bin"
            with patch("networking._open_allowlisted", return_value=io.BytesIO(payload)):
                with self.assertRaisesRegex(RuntimeError, "size did not match"):
                    networking.download_verified_file(
                        "https://github.com/example/project/releases/download/v1/asset.bin",
                        destination,
                        expected_sha256=hashlib.sha256(payload).hexdigest(),
                        expected_size=len(payload) + 1,
                        maximum_size=1024,
                        headers={},
                    )


if __name__ == "__main__":
    unittest.main()
