import re
import unittest
from pathlib import Path

import updater


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ProjectConsistencyTests(unittest.TestCase):
    def test_all_third_party_license_files_are_required_by_updates(self):
        license_directory = PROJECT_ROOT / "third_party_licenses"
        distributed_files = {item.name for item in license_directory.iterdir() if item.is_file()}
        self.assertEqual(distributed_files, set(updater.REQUIRED_LICENSE_FILES))

    def test_public_installer_requires_every_update_package_file(self):
        installer = (PROJECT_ROOT / "install.ps1").read_text(encoding="utf-8")
        for name in updater.REQUIRED_PACKAGE_FILES:
            self.assertIn(f'"{name}"', installer)

    def test_app_version_uses_release_version_shape(self):
        app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
        match = re.search(r'^APP_VERSION = "([^"]+)"$', app_source, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(updater.parse_version(match.group(1)), tuple(map(int, match.group(1).split("."))))

    def test_header_shows_version_and_uses_a_readable_update_label(self):
        app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('text=f"v{APP_VERSION}"', app_source)
        self.assertIn('text="Update"', app_source)
        self.assertNotIn('text="↻ Update"', app_source)

    def test_uninstaller_targets_the_installed_executable_path(self):
        uninstaller = (
            PROJECT_ROOT / "packaging" / "Uninstall-YT-DLP-GUI.ps1"
        ).read_text(encoding="utf-8")
        self.assertIn("ExecutablePath", uninstaller)
        self.assertIn("$installedExecutable", uninstaller)
        self.assertNotIn("taskkill", uninstaller.lower())

    def test_transactional_installer_checks_every_license_file(self):
        installer = (
            PROJECT_ROOT / "packaging" / "Install-YT-DLP-GUI.ps1"
        ).read_text(encoding="utf-8")
        for name in updater.REQUIRED_LICENSE_FILES:
            self.assertIn(f'"{name}"', installer)

    def test_legacy_updater_compatibility_is_preserved(self):
        installer = (
            PROJECT_ROOT / "packaging" / "Install-YT-DLP-GUI.bat"
        ).read_text(encoding="ascii")
        self.assertIn("if exist \"%INSTALLER%\"", installer)
        self.assertIn("EXPECTED_HASH=__EXPECTED_HASH__", installer)
        self.assertIn("APP_VERSION=__APP_VERSION__", installer)
        self.assertIn("YT_DLP_GUI_NO_LAUNCH", installer)

    def test_frozen_bundle_contains_legal_notices(self):
        spec = (PROJECT_ROOT / "YT-DLP-GUI.spec").read_text(encoding="utf-8-sig")
        self.assertIn("THIRD_PARTY_NOTICES.md", spec)
        self.assertIn("third_party_licenses", spec)

    def test_release_workflow_runs_frozen_gui_smoke_test(self):
        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "release.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("--verify-gui", workflow)
        self.assertIn("PYINSTALLER_RESET_ENVIRONMENT", workflow)
        self.assertIn("_MEI-deleted-restart-state", workflow)
        self.assertIn("GITHUB_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("YT_DLP_GUI_VERIFY_LOG", workflow)


if __name__ == "__main__":
    unittest.main()
