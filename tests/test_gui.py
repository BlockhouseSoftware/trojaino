from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from aishield.gui import default_output_dir, report_paths, run_scan, write_reports


class GuiSupportTests(unittest.TestCase):
    def make_project(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="aishield-gui-test-"))

    def test_default_output_dir_is_adjacent_to_selected_target(self):
        project = self.make_project()
        source = project / "src" / "app.py"
        source.parent.mkdir()
        source.write_text("print('ok')", encoding="utf-8")

        self.assertEqual(default_output_dir(project), project / "TrojainoReports")
        self.assertEqual(default_output_dir(source), project / "src" / "TrojainoReports")

    def test_default_output_dir_stays_outside_a_git_repository(self):
        parent = self.make_project()
        repository = parent / "client-project"
        repository.mkdir()
        (repository / ".git").mkdir()
        source = repository / "src" / "app.py"
        source.parent.mkdir()
        source.write_text("print('ok')", encoding="utf-8")

        self.assertEqual(default_output_dir(repository), parent / "TrojainoReports")
        self.assertEqual(default_output_dir(source), parent / "TrojainoReports")

    def test_report_paths_are_target_named_timestamped_and_collision_safe(self):
        project = self.make_project() / "client project!"
        project.mkdir()
        output = self.make_project() / "reports"
        moment = datetime(2026, 8, 12, 22, 15, 30, tzinfo=timezone.utc)

        html_path, json_path = report_paths(project, output, moment=moment)
        self.assertEqual(html_path.name, "client-project-20260812-221530.html")
        self.assertEqual(json_path.name, "client-project-20260812-221530.json")

        output.mkdir()
        html_path.write_text("existing", encoding="utf-8")
        next_html, next_json = report_paths(project, output, moment=moment)
        self.assertEqual(next_html.name, "client-project-20260812-221530-2.html")
        self.assertEqual(next_json.name, "client-project-20260812-221530-2.json")

    def test_run_scan_uses_selected_budget_and_preserves_preflight(self):
        project = self.make_project()
        (project / "app.py").write_text("print('ok')", encoding="utf-8")

        result = run_scan(project, profile="default", budget_name="large")

        self.assertEqual(result.verdict, "NO CRITICAL RISKS FOUND")
        self.assertTrue(result.complete)
        self.assertIsNotNone(result.preflight)
        self.assertEqual(result.budget["preset"], "large")
        self.assertEqual(result.budget["max_elapsed_seconds"], 120.0)

    def test_write_reports_creates_parent_directory_and_machine_readable_json(self):
        project = self.make_project()
        (project / "app.py").write_text("print('ok')", encoding="utf-8")
        result = run_scan(project, profile="default", budget_name="standard")
        output = self.make_project() / "nested" / "reports"
        html_path = output / "report.html"
        json_path = output / "report.json"

        write_reports(result, html_path=html_path, json_path=json_path)

        self.assertTrue(html_path.exists())
        html_text = html_path.read_text(encoding="utf-8")
        self.assertIn("Trojaino · Scan Report", html_text)
        self.assertIn("Blockhouse Software", html_text)
        self.assertIn("Scanned:", html_text)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["target"], str(project.absolute()))
        self.assertEqual(payload["budget"]["preset"], "standard")
        self.assertIsNotNone(payload["scanned_at"])


if __name__ == "__main__":
    unittest.main()
