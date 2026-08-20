from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trojaino.report import render_json
from trojaino.scanner import scan_path


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


if __name__ == "__main__":
    unittest.main()
