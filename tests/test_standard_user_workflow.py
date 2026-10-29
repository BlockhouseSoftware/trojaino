import unittest
from pathlib import Path

class TestWindowsStandardUserCI(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1]
        self.ps_parent = self.root / "scripts" / "windows_standard_user.ps1"
        self.ps_child = self.root / "scripts" / "windows_standard_user_child.ps1"
        self.yml_file = self.root / ".github" / "workflows" / "windows-standard-user.yml"

    def test_files_exist(self):
        self.assertTrue(self.ps_parent.exists(), "Parent script missing")
        self.assertTrue(self.ps_child.exists(), "Child script missing")
        self.assertTrue(self.yml_file.exists(), "Workflow file missing")

    def test_parent_script_content(self):
        content = self.ps_parent.read_text()
        required = ["EnvironmentVariables.Clear()", "LoadUserProfile = $true",
                    "UseShellExecute = $false", "New-LocalUser", "Remove-LocalUser"]
        for item in required:
            self.assertIn(item, content, f"Missing {item} in parent script")

    def test_child_script_content(self):
        content = self.ps_child.read_text()
        required = ["IsInRole", "S-1-5-32-544"]
        for item in required:
            self.assertIn(item, content, f"Missing {item} in child script")
        self.assertIn("scripts/smoke_plugin_install.py", content)
        self.assertIn("--candidate-git", content)

    def test_workflow_config(self):
        content = self.yml_file.read_text()
        self.assertIn("persist-credentials: false", content)
        self.assertIn("contents: read", content)
        self.assertIn("windows-11-arm", content)
        self.assertIn("ci/windows11-standard-user", content)
        self.assertNotIn("secrets.", content)
        self.assertNotIn("live_gate_check.py", content)

if __name__ == '__main__':
    unittest.main()
