from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trojaino.contributions as contributions
from trojaino.contributions import (
    ContributionError,
    build_contribution_payload,
    build_contribution_payload_from_report,
    contribution_preview,
    delete_contribution,
    submit_contribution,
)
from trojaino.scanner import scan_path


class _FakeResponse:
    def __init__(self, body: bytes = b'{"receipt_id":"receipt-123","deletion_token":"delete-456"}', status: int = 201):
        self.body = body
        self.status = status

    def read(self, size: int = -1) -> bytes:
        return self.body[:size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ContributionTests(unittest.TestCase):
    def make_project(self) -> Path:
        project = Path(tempfile.mkdtemp(prefix="trojaino-contribution-test-"))
        (project / ".env").write_text("OPENAI_API_KEY=sk-not-a-real-secret-1234567890", encoding="utf-8")
        (project / "src").mkdir()
        (project / "src" / "app.py").write_text("print('hello')", encoding="utf-8")
        return project

    def test_payload_is_aggregate_and_excludes_all_local_identifiers_and_evidence(self):
        project = self.make_project()
        result = scan_path(project)

        payload = build_contribution_payload(result)
        preview = contribution_preview(payload)

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["verdict"], "DO NOT RUN")
        self.assertEqual(payload["files_scanned_band"], "0-10")
        self.assertIn("SECRET_ENV_FILE_COMMITTED", preview)
        for forbidden in (str(project), ".env", "app.py", "OPENAI_API_KEY", "sk-not-a-real-secret"):
            self.assertNotIn(forbidden, preview)
        self.assertNotIn('"evidence"', preview)
        self.assertNotIn('"target"', preview)
        self.assertNotIn('"file"', preview)
        self.assertNotIn('"line"', preview)

    def test_payload_from_saved_report_reapplies_the_allowlist(self):
        project = self.make_project()
        report = scan_path(project).to_dict()
        report["target"] = "/private/company/repo"
        report["findings"][0]["evidence"] = "super-secret"
        report["findings"][0]["file"] = "do-not-send.py"

        payload = build_contribution_payload_from_report(report)
        preview = contribution_preview(payload)

        self.assertNotIn("/private/company/repo", preview)
        self.assertNotIn("super-secret", preview)
        self.assertNotIn("do-not-send.py", preview)

    def test_report_with_untrusted_text_fields_cannot_be_forwarded(self):
        report = {
            "scanner_version": "0.1.1",
            "profile": "default",
            "verdict": "CAUTION",
            "complete": True,
            "files_scanned": 1,
            "findings": [{
                "id": "RULE_WITH_SOURCE_PATH",
                "severity": "high",
                "confidence": "high",
                "context": "application_code",
                "disposition": "actionable",
            }],
            "capabilities": [],
            "issues": [],
        }

        with self.assertRaisesRegex(ContributionError, "finding rule id"):
            build_contribution_payload_from_report(report)

    def test_submit_uses_small_json_post_to_the_compiled_official_endpoint(self):
        payload = build_contribution_payload(scan_path(self.make_project()))
        with self.assertRaisesRegex(ContributionError, "HTTPS"):
            with patch.object(contributions, "OFFICIAL_CONTRIBUTION_ENDPOINT", "http://example.test/contributions"):
                submit_contribution(payload)

        endpoint = "https://contribute.example.test/v1/scan-statistics"
        with (
            patch.object(contributions, "OFFICIAL_CONTRIBUTION_ENDPOINT", endpoint),
            patch("trojaino.contributions.urlopen", return_value=_FakeResponse()) as mocked_open,
        ):
            receipt = submit_contribution(payload)

        self.assertEqual(receipt.receipt_id, "receipt-123")
        self.assertEqual(receipt.deletion_token, "delete-456")
        request = mocked_open.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertLess(len(request.data), 64 * 1024)
        posted = json.loads(request.data.decode("utf-8"))
        self.assertEqual(posted["contribution_id"], payload["contribution_id"])

    def test_delete_uses_the_fixed_official_endpoint_and_confirms_deletion(self):
        endpoint = "https://contribute.example.test/v1/scan-statistics"
        with (
            patch.object(contributions, "OFFICIAL_CONTRIBUTION_ENDPOINT", endpoint),
            patch("trojaino.contributions.urlopen", return_value=_FakeResponse(b'{"deleted":true}', status=200)) as mocked_open,
        ):
            delete_contribution("receipt-123", "delete-456")

        request = mocked_open.call_args.args[0]
        self.assertEqual(request.get_method(), "DELETE")
        self.assertEqual(request.full_url, f"{endpoint}/receipt-123")
        self.assertEqual(json.loads(request.data.decode("utf-8")), {"deletion_token": "delete-456"})


if __name__ == "__main__":
    unittest.main()
