import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import runtime_dependencies


class RuntimeDependencyTests(unittest.TestCase):
    def test_ffmpeg_setup_extracts_only_required_runtime_files(self):
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temporary_file:
            archive_source = Path(temporary_file.name)
        self.addCleanup(archive_source.unlink, missing_ok=True)
        with zipfile.ZipFile(archive_source, "w") as archive:
            archive.writestr("build/bin/ffmpeg.exe", b"processor")
            archive.writestr("build/bin/ffprobe.exe", b"probe")
            archive.writestr("build/LICENSE.txt", b"license")
            archive.writestr("build/unexpected.exe", b"ignored")

        def provide_archive(_api, _name, _maximum, destination, _log):
            shutil.copyfile(archive_source, destination)

        with tempfile.TemporaryDirectory() as temporary_directory, patch(
            "runtime_dependencies._download_asset", side_effect=provide_archive
        ), patch("runtime_dependencies._ffmpeg_is_ready", return_value=True):
            executable = runtime_dependencies.ensure_ffmpeg_runtime(
                lambda _message: None,
                Path(temporary_directory),
            )
            extracted = {item.name for item in executable.parent.iterdir()}

        self.assertEqual(
            extracted,
            {"ffmpeg.exe", "ffprobe.exe", "FFMPEG-LICENSE.txt"},
        )

    def test_archive_member_lookup_rejects_duplicate_names(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive_path = Path(temporary_directory) / "duplicate.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("one/tool.exe", b"one")
                archive.writestr("two/tool.exe", b"two")
            with zipfile.ZipFile(archive_path) as archive:
                with self.assertRaisesRegex(RuntimeError, "exactly one"):
                    runtime_dependencies._single_archive_member(archive, "tool.exe")


if __name__ == "__main__":
    unittest.main()
