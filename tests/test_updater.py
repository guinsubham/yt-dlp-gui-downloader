import hashlib
import io
import json
import shutil
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import updater


class UpdaterTests(unittest.TestCase):
    def test_parse_version_accepts_release_tags(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("1.2.3"), (1, 2, 3))

    def test_parse_version_rejects_unsupported_values(self):
        with self.assertRaises(ValueError):
            updater.parse_version("1.2")

    def test_get_latest_release_requires_github_digest(self):
        payload = {
            "tag_name": "v2.0.0",
            "assets": [{
                "name": updater.WINDOWS_ASSET_NAME,
                "browser_download_url": "https://github.com/example/project/releases/download/v2/update.zip",
                "digest": "",
                "size": 100,
            }],
        }
        with patch("networking._open_allowlisted", return_value=io.BytesIO(json.dumps(payload).encode())):
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                updater.get_latest_release()

    def test_prepare_update_verifies_and_extracts_only_required_files(self):
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            for name in updater.REQUIRED_PACKAGE_FILES:
                archive.writestr(name, f"contents of {name}")
            archive.writestr("ignored.txt", "not part of the installer")
        archive_bytes = archive_buffer.getvalue()
        release = updater.ReleaseInfo(
            tag="v2.0.0",
            version=(2, 0, 0),
            download_url="https://github.com/example/project/releases/download/v2/update.zip",
            sha256=hashlib.sha256(archive_bytes).hexdigest(),
            size=len(archive_bytes),
        )

        with patch("networking._open_allowlisted", return_value=io.BytesIO(archive_bytes)):
            prepared = updater.prepare_update(release, lambda _message: None)
        try:
            extracted = {item.name for item in prepared.installer_path.parent.iterdir()}
            self.assertEqual(extracted, set(updater.REQUIRED_PACKAGE_FILES))
        finally:
            shutil.rmtree(prepared.temporary_directory, ignore_errors=True)

    def test_launch_update_builds_detached_wait_and_restart_command(self):
        release = updater.ReleaseInfo(
            "v2.0.0",
            (2, 0, 0),
            "https://github.com/example/project/releases/download/v2/update.zip",
            "0" * 64,
            1,
        )
        prepared = updater.PreparedUpdate(
            release=release,
            temporary_directory=Path(r"C:\Temp\YT-DLP-GUI-update"),
            installer_path=Path(r"C:\Temp\YT-DLP-GUI-update\Install-YT-DLP-GUI.bat"),
        )

        powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
        with patch("updater._windows_powershell_path", return_value=powershell), patch(
            "updater.subprocess.Popen"
        ) as popen:
            updater.launch_update_after_exit(prepared, 12345, Path(sys.executable))

        arguments = popen.call_args.args[0]
        command = arguments[-1]
        self.assertEqual(arguments[0], str(powershell))
        self.assertIn("Wait-Process -Id 12345", command)
        self.assertIn("YT_DLP_GUI_SILENT", command)
        self.assertIn(str(prepared.installer_path), command)
        self.assertIn(str(Path(sys.executable)), command)

    def test_prepare_update_rejects_oversized_archive_member(self):
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            for name in updater.REQUIRED_PACKAGE_FILES:
                archive.writestr(name, "x")
        archive_bytes = archive_buffer.getvalue()
        release = updater.ReleaseInfo(
            tag="v2.0.0",
            version=(2, 0, 0),
            download_url="https://github.com/example/project/releases/download/v2/update.zip",
            sha256=hashlib.sha256(archive_bytes).hexdigest(),
            size=len(archive_bytes),
        )

        with patch("networking._open_allowlisted", return_value=io.BytesIO(archive_bytes)), patch(
            "updater.MAX_MEMBER_SIZE", 0
        ):
            with self.assertRaisesRegex(RuntimeError, "extraction limit"):
                updater.prepare_update(release, lambda _message: None)


if __name__ == "__main__":
    unittest.main()
