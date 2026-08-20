from __future__ import annotations

import unittest
from pathlib import Path


INSTALLER_SCRIPT = Path(__file__).parents[1] / "installer" / "trojaino.iss"
WORKFLOW = Path(__file__).parents[1] / ".github" / "workflows" / "windows-installer.yml"


class WindowsInstallerDefinitionTests(unittest.TestCase):
    def test_installer_is_user_scoped_and_versioned(self):
        script = INSTALLER_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("OutputBaseFilename=Trojaino-Setup-{#AppVersion}", script)
        self.assertIn("DefaultDirName={localappdata}\\Programs\\Trojaino", script)
        self.assertIn("PrivilegesRequired=lowest", script)
        self.assertIn("ArchitecturesAllowed=x64compatible", script)
        self.assertIn("Source: \"{#SourceDir}\\*\"; DestDir: \"{app}\"", script)

    def test_installer_adds_and_removes_only_its_user_path_entry(self):
        script = INSTALLER_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("procedure AddToUserPath", script)
        self.assertIn("procedure RemoveFromUserPath", script)
        self.assertIn("UserPathContains(Directory)", script)
        self.assertIn("CurUninstallStep = usPostUninstall", script)
        self.assertIn("RegWriteExpandStringValue(HKCU, 'Environment', 'Path'", script)

    def test_windows_workflow_builds_installs_tests_and_uninstalls(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("choco install innosetup", workflow)
        self.assertIn("iscc", workflow)
        self.assertIn("/VERYSILENT", workflow)
        self.assertIn("tests/fixtures/clean-project", workflow)
        self.assertIn("tests/fixtures/bad-node-app", workflow)
        self.assertIn("unins000.exe", workflow)
        self.assertIn("Trojaino-Setup-$version.exe", workflow)


if __name__ == "__main__":
    unittest.main()
