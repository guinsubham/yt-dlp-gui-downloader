import hashlib
import io
import json
import shutil
import sys
import tempfile
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

    def test_get_latest_release_rejects_malformed_assets(self):
        payload = {"tag_name": "v2.0.0", "assets": "not-a-list"}
        with patch("networking._open_allowlisted", return_value=io.BytesIO(json.dumps(payload).encode())):
            with self.assertRaisesRegex(RuntimeError, "malformed release metadata"):
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
            package_directory = prepared.installer_path.parent
            extracted = {
                item.relative_to(package_directory).as_posix()
                for item in package_directory.rglob("*")
                if item.is_file()
            }
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
        with tempfile.TemporaryDirectory() as temporary_directory:
            update_directory = Path(temporary_directory)
            prepared = updater.PreparedUpdate(
                release=release,
                temporary_directory=update_directory,
                installer_path=update_directory / "Install-YT-DLP-GUI.bat",
            )
            powershell = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
            installed_executable = Path(r"C:\Users\Example\AppData\Local\Programs\YT-DLP-GUI\YT-DLP-GUI.exe")
            update_log = update_directory / "update.log"
            with patch("updater._windows_powershell_path", return_value=powershell), patch(
                "updater._installed_executable_path", return_value=installed_executable
            ), patch("updater._update_log_path", return_value=update_log), patch(
                "updater.subprocess.Popen"
            ) as popen:
                returned_log = updater.launch_update_after_exit(prepared, 12345, Path(sys.executable))

            arguments = popen.call_args.args[0]
            runner_path = Path(arguments[-1])
            runner = runner_path.read_text(encoding="utf-8-sig")
            self.assertEqual(arguments[0], str(powershell))
            self.assertEqual(arguments[-2], "-File")
            self.assertEqual(returned_log, update_log)
            self.assertIn("Wait-Process -Id $processId", runner)
            self.assertIn("$processId = 12345", runner)
            self.assertIn("YT_DLP_GUI_SILENT", runner)
            self.assertIn("YT_DLP_GUI_NO_LAUNCH", runner)
            self.assertIn(str(prepared.installer_path), runner)
            self.assertIn("Start-UpdatedApplication $restartPath", runner)
            self.assertIn(str(installed_executable), runner)
            self.assertIn(str(Path(sys.executable)), runner)

    def test_packaged_installer_defers_launch_during_an_in_app_update(self):
        installer_path = Path(__file__).resolve().parents[1] / "packaging" / "Install-YT-DLP-GUI.ps1"
        installer = installer_path.read_text(encoding="utf-8")

        self.assertIn(
            "if (-not $env:YT_DLP_GUI_NO_LAUNCH)",
            installer,
        )

    def test_prepare_update_rejects_unsafe_archive_paths(self):
        archive_buffer = io.BytesIO()
        with zipfile.ZipFile(archive_buffer, "w") as archive:
            for name in updater.REQUIRED_PACKAGE_FILES:
                archive.writestr(name, "x")
            archive.writestr("../unexpected.txt", "unsafe")
        archive_bytes = archive_buffer.getvalue()
        release = updater.ReleaseInfo(
            tag="v2.0.0",
            version=(2, 0, 0),
            download_url="https://github.com/example/project/releases/download/v2/update.zip",
            sha256=hashlib.sha256(archive_bytes).hexdigest(),
            size=len(archive_bytes),
        )

        with patch("networking._open_allowlisted", return_value=io.BytesIO(archive_bytes)):
            with self.assertRaisesRegex(RuntimeError, "unsafe archive path"):
                updater.prepare_update(release, lambda _message: None)

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
