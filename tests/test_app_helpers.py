import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class AppHelperTests(unittest.TestCase):
    def test_format_eta_handles_hours_and_invalid_values(self):
        self.assertEqual(app.format_eta(3661), "01:01:01")
        self.assertEqual(app.format_eta(-1), "00:00:00")
        self.assertEqual(app.format_eta("invalid"), "--:--:--")

    def test_format_bytes_uses_binary_units(self):
        self.assertEqual(app.format_bytes(1024), "1.0 KB")
        self.assertEqual(app.format_bytes(1024 * 1024), "1.0 MB")
        self.assertEqual(app.format_bytes(None), "--")

    def test_presets_have_a_format_and_supported_merge_container(self):
        self.assertGreaterEqual(len(app.PRESETS), 7)
        for preset in app.PRESETS.values():
            self.assertTrue(preset.get("format"))
            if "merge_output_format" in preset:
                self.assertRegex(preset["merge_output_format"], r"^(mp4|mkv|mp4/mkv)$")

    def test_media_url_validation_accepts_web_urls_without_credentials(self):
        self.assertTrue(app.is_supported_media_url("https://example.com/watch?v=1"))
        self.assertFalse(app.is_supported_media_url("file:///C:/private.txt"))
        self.assertFalse(app.is_supported_media_url("https://user:secret@example.com/video"))

    def test_legacy_update_materializes_bundled_license_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            resources = root / "resources"
            installation = root / "installation"
            (resources / "third_party_licenses").mkdir(parents=True)
            (resources / "third_party_licenses" / "example-LICENSE.txt").write_text(
                "license",
                encoding="utf-8",
            )
            (resources / "THIRD_PARTY_NOTICES.md").write_text("notices", encoding="utf-8")
            installation.mkdir()

            def fake_resource_path(name):
                return resources / name

            with patch.object(app.sys, "frozen", True, create=True), patch(
                "app.resource_path",
                side_effect=fake_resource_path,
            ), patch("app.app_dir", return_value=installation):
                app.ensure_installed_legal_files(lambda _message: None)

            self.assertTrue(
                (installation / "third_party_licenses" / "example-LICENSE.txt").is_file()
            )
            self.assertTrue((installation / "THIRD_PARTY_NOTICES.md").is_file())


if __name__ == "__main__":
    unittest.main()
