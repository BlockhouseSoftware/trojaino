from __future__ import annotations

import tempfile
import unittest
import importlib.util
import hashlib
import os
from pathlib import Path

from trojaino.report import render_json
from trojaino.scanner import scan_path


CHECKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_release_self_scan.py"
CHECKER_SPEC = importlib.util.spec_from_file_location("release_self_scan", CHECKER_PATH)
if CHECKER_SPEC is None or CHECKER_SPEC.loader is None:
    raise RuntimeError(f"cannot load release self-scan checker: {CHECKER_PATH}")
CHECKER = importlib.util.module_from_spec(CHECKER_SPEC)
CHECKER_SPEC.loader.exec_module(CHECKER)


class ReleaseProfileTests(unittest.TestCase):
    def make_project(self, files: dict[str, str]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="trojaino-release-"))
        for relative_path, content in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    def test_release_profile_excludes_development_corpus_but_keeps_shipped_files(self):
        project = self.make_project({
            "tests/fixtures/bad/.env": "OPENAI_API_KEY=sk-test-repository-fixture-value\n",
            "reference/scan-reports/example.json": '{"evidence": "credentials"}',
            "benchmark/artifacts/finding-heavy.json": '{"evidence": "process.env.API_TOKEN"}',
            "trojaino/core.py": "def main():\n    return 0\n",
            "pyproject.toml": '[project]\nname = "example"\n',
        })

        default_result = scan_path(project)
        release_result = scan_path(project, profile="release")

        self.assertEqual(default_result.verdict, "DO NOT RUN")
        self.assertEqual(release_result.profile, "release")
        self.assertEqual(release_result.verdict, "NO CRITICAL RISKS FOUND")
        self.assertEqual(release_result.files_scanned, 2)
        self.assertIn('"profile": "release"', render_json(release_result))

    def test_release_profile_scans_shipped_installer_source_formats(self):
        project = self.make_project({
            "installer/Setup.cs": "public class Setup {}\n",
            "installer/Setup.csproj": "<Project />\n",
            "installer/setup.iss": "[Setup]\nAppName=Trojaino\n",
        })

        result = scan_path(project, profile="release")

        self.assertEqual(result.files_scanned, 3)
        self.assertTrue(result.complete)

    def test_python_rule_regex_declarations_are_not_mcp_runtime_proof(self):
        project = self.make_project({
            "trojaino/rules/mcp.py": """
import re
MCP_RUNTIME_RE = re.compile(r'\\bMcpServer\\b|@modelcontextprotocol')
SHELL_TOOL_RE = re.compile(r'\\bexec\\b')
""",
        })

        result = scan_path(project)

        self.assertFalse(
            {"MCP_SHELL_TOOL", "MCP_FILESYSTEM_TOOL", "MCP_CREDENTIAL_ACCESS"}
            & {finding.id for finding in result.findings}
        )
        self.assertFalse(result.capabilities)

    def test_self_scan_baseline_allows_only_the_reviewed_findings(self):
        report = {
            "profile": "release",
            "complete": True,
            "findings": [
                {"id": "PY_EVAL_EXEC", "severity": "high", "file": "plugins/trojaino/scripts/preflight.py", "line": 21, "fingerprint": "a"},
            ],
        }
        baseline = {
            "version": 1,
            "profile": "release",
            "findings": [
                {"id": "PY_EVAL_EXEC", "severity": "high", "file": "plugins/trojaino/scripts/preflight.py", "line": 21, "fingerprint": "a", "review": "Constrained sealed runtime only."},
            ],
        }

        self.assertEqual(CHECKER.verify_report(report, baseline), [])
        del baseline["findings"][0]["review"]
        self.assertEqual(CHECKER.verify_report(report, baseline), ["baseline findings require reviewed rationale"])
        baseline["findings"][0]["review"] = "Constrained sealed runtime only."
        report["findings"][0]["severity"] = "critical"
        self.assertEqual(CHECKER.verify_report(report, baseline), ["unexpected or changed self-scan findings"])

    def test_self_scan_baseline_cannot_be_changed_without_shipped_source_change(self):
        self.assertFalse(CHECKER.has_shipped_source_change(["reference/release-self-scan-baseline.json"]))
        self.assertFalse(CHECKER.has_shipped_source_change(["tests/test_release_profile.py", "reference/release-self-scan-baseline.json"]))
        self.assertTrue(CHECKER.has_shipped_source_change(["plugins/trojaino/scripts/preflight.py", "reference/release-self-scan-baseline.json"]))

    def test_corrective_inventory_refresh_requires_only_stale_source_hashes(self):
        root = self.make_project({
            "scripts/runtime.py": "safe = True\n",
            "scripts/unchanged.py": "still_safe = True\n",
        })
        current_digest = hashlib.sha256((root / "scripts/runtime.py").read_bytes()).hexdigest()
        unchanged_digest = hashlib.sha256((root / "scripts/unchanged.py").read_bytes()).hexdigest()
        base_baseline = {
            "version": 1,
            "profile": "release",
            "findings": [],
            "source_inventory": [
                {"file": "scripts/runtime.py", "sha256": "0" * 64},
                {"file": "scripts/unchanged.py", "sha256": unchanged_digest},
            ],
        }
        refreshed_baseline = {
            **base_baseline,
            "source_inventory": [
                {"file": "scripts/runtime.py", "sha256": current_digest},
                {"file": "scripts/unchanged.py", "sha256": unchanged_digest},
            ],
        }

        self.assertEqual(
            CHECKER.verify_corrective_inventory_refresh(
                root,
                refreshed_baseline,
                base_baseline,
                [".github/release-self-scan-baseline.json"],
            ),
            [],
        )
        refreshed_baseline["findings"] = [{"id": "NEW"}]
        self.assertEqual(
            CHECKER.verify_corrective_inventory_refresh(
                root,
                refreshed_baseline,
                base_baseline,
                [".github/release-self-scan-baseline.json"],
            ),
            ["corrective self-scan baseline refresh changed reviewed findings or policy"],
        )

    def test_strict_baseline_json_rejects_duplicate_keys(self):
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            CHECKER.strict_json_load('{"version": 1, "version": 1}')

    def test_corrective_inventory_refresh_rejects_duplicate_inventory_entries(self):
        root = self.make_project({"scripts/runtime.py": "safe = True\n"})
        digest = hashlib.sha256((root / "scripts/runtime.py").read_bytes()).hexdigest()
        baseline = {
            "version": 1,
            "profile": "release",
            "findings": [],
            "source_inventory": [
                {"file": "scripts/runtime.py", "sha256": digest},
                {"file": "scripts/runtime.py", "sha256": digest},
            ],
        }

        self.assertEqual(
            CHECKER.verify_corrective_inventory_refresh(
                root, baseline, baseline, [".github/release-self-scan-baseline.json"]
            ),
            ["corrective self-scan baseline refresh has an invalid source inventory"],
        )

    def test_self_scan_baseline_rejects_unsorted_source_inventory(self):
        root = self.make_project({
            "scripts/a.py": "a = 1\n",
            "scripts/b.py": "b = 1\n",
        })
        inventory = CHECKER.shipped_source_inventory(root)
        self.assertEqual(
            CHECKER.verify_source_inventory(root, {"source_inventory": list(reversed(inventory))}),
            ["self-scan baseline source inventory is invalid"],
        )

    def test_self_scan_baseline_binds_reviewed_shipped_source_bytes(self):
        root = self.make_project({
            "scripts/runtime.py": "safe = True\n",
            "scripts/__pycache__/runtime.cpython-311.pyc": "not shipped source",
            "installer/Setup.cs": "public class Setup {}\n",
            "schemas/report.json": "{}\n",
            "requirements/test.txt": "\n",
        })
        digest = hashlib.sha256((root / "scripts/runtime.py").read_bytes()).hexdigest()
        installer_digest = hashlib.sha256((root / "installer/Setup.cs").read_bytes()).hexdigest()
        schema_digest = hashlib.sha256((root / "schemas/report.json").read_bytes()).hexdigest()
        requirements_digest = hashlib.sha256((root / "requirements/test.txt").read_bytes()).hexdigest()
        baseline = {"source_inventory": [
            {"file": "installer/Setup.cs", "sha256": installer_digest},
            {"file": "requirements/test.txt", "sha256": requirements_digest},
            {"file": "schemas/report.json", "sha256": schema_digest},
            {"file": "scripts/runtime.py", "sha256": digest},
        ]}

        self.assertEqual(CHECKER.verify_source_inventory(root, baseline), [])
        (root / "scripts/runtime.py").write_text("safe = False\n", encoding="utf-8")
        self.assertEqual(CHECKER.verify_source_inventory(root, baseline), ["reviewed shipped-source inventory changed"])

    def test_ci_runs_baseline_checker_after_expected_self_scan_verdict(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("scan_rc=$?", workflow)
        self.assertIn('"$scan_rc" -ne 2', workflow)
        self.assertIn("scripts/check_release_self_scan.py", workflow)
        self.assertIn(".github/release-self-scan-baseline.json", workflow)
        self.assertIn("if: github.event_name == 'pull_request'", workflow)
        self.assertIn("github.event.pull_request.base.sha", workflow)
        self.assertIn("--base-baseline", workflow)
        self.assertIn("git show \"$BASE_SHA:.github/release-self-scan-baseline.json\"", workflow)
        self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", workflow)
        self.assertIn("actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97", workflow)
        self.assertNotIn("github.event.before", workflow)
        self.assertIn("unable to establish a trusted base revision", workflow)

    def test_self_scan_baseline_rejects_shipped_source_symlinks(self):
        root = self.make_project({"scripts/runtime.py": "safe = True\n"})
        digest = hashlib.sha256((root / "scripts/runtime.py").read_bytes()).hexdigest()
        baseline = {"source_inventory": [{"file": "scripts/runtime.py", "sha256": digest}]}
        os.symlink("runtime.py", root / "scripts" / "runtime-link.py")

        self.assertEqual(CHECKER.verify_source_inventory(root, baseline), ["reviewed shipped-source inventory changed"])

    def test_self_scan_baseline_rejects_symlinked_shipped_source_root(self):
        root = self.make_project({"outside/runtime.py": "safe = True\n"})
        os.symlink(root / "outside", root / "scripts")

        self.assertEqual(CHECKER.verify_source_inventory(root, {"source_inventory": []}), ["reviewed shipped-source inventory changed"])

    def test_self_scan_policy_files_require_security_owner_review(self):
        owners = (Path(__file__).resolve().parents[1] / ".github/CODEOWNERS").read_text(encoding="utf-8")
        self.assertIn("/.github/release-self-scan-baseline.json @joseamayo", owners)
        self.assertIn("/scripts/check_release_self_scan.py @joseamayo", owners)
        self.assertIn("/.github/workflows/ci.yml @joseamayo", owners)
        self.assertIn("/.github/CODEOWNERS @joseamayo", owners)


if __name__ == "__main__":
    unittest.main()


class InventoryOrderingTests(unittest.TestCase):
    """The generated inventory must satisfy the validator that consumes it."""

    def test_directory_beside_same_stemmed_file_stays_string_sorted(self):
        import runpy
        checker = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'scripts/check_release_self_scan.py'))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'trojaino/claude/payload').mkdir(parents=True)
            (root / 'trojaino/claude/payload.py').write_text('x')
            (root / 'trojaino/claude/payload/LICENSE').write_text('y')
            (root / 'trojaino/claude/payload/plugin.json').write_text('{}')
            inventory = checker['shipped_source_inventory'](root)
            names = [entry['file'] for entry in inventory]
            self.assertEqual(names, sorted(names), 'inventory must be sorted as strings')
            self.assertIsNotNone(checker['inventory_map'](inventory),
                                 'inventory_map must accept a freshly generated inventory')
