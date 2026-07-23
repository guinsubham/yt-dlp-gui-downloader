import os
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

    def test_ffmpeg_setup_restores_previous_runtime_if_activation_fails(self):
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temporary_file:
            archive_source = Path(temporary_file.name)
        self.addCleanup(archive_source.unlink, missing_ok=True)
        with zipfile.ZipFile(archive_source, "w") as archive:
            archive.writestr("build/bin/ffmpeg.exe", b"new processor")
            archive.writestr("build/bin/ffprobe.exe", b"new probe")
            archive.writestr("build/LICENSE.txt", b"new license")

        def provide_archive(_api, _name, _maximum, destination, _log):
            shutil.copyfile(archive_source, destination)

        real_replace = os.replace
        activation_attempts = 0

        def fail_new_runtime_activation(source, destination):
            nonlocal activation_attempts
            activation_attempts += 1
            if activation_attempts == 2:
                raise OSError("simulated activation failure")
            return real_replace(source, destination)

        with tempfile.TemporaryDirectory() as temporary_directory:
            runtime_root = Path(temporary_directory)
            old_runtime = runtime_root / "ffmpeg"
            old_runtime.mkdir()
            (old_runtime / "ffmpeg.exe").write_bytes(b"old processor")
            (old_runtime / "ffprobe.exe").write_bytes(b"old probe")
            (old_runtime / "FFMPEG-LICENSE.txt").write_bytes(b"old license")

            with patch("runtime_dependencies._download_asset", side_effect=provide_archive), patch(
                "runtime_dependencies._ffmpeg_is_ready",
                side_effect=[False, True],
            ), patch("runtime_dependencies.os.replace", side_effect=fail_new_runtime_activation):
                with self.assertRaisesRegex(OSError, "simulated activation failure"):
                    runtime_dependencies.ensure_ffmpeg_runtime(
                        lambda _message: None,
                        runtime_root,
                    )

            self.assertEqual((old_runtime / "ffmpeg.exe").read_bytes(), b"old processor")


if __name__ == "__main__":
    unittest.main()
