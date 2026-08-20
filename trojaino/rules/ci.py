from __future__ import annotations

import re
from pathlib import Path

from trojaino.file_utils import line_for_index
from trojaino.models import Finding, relpath


CI_FILENAMES = {".gitlab-ci.yml", ".gitlab-ci.yaml", "azure-pipelines.yml", "azure-pipelines.yaml"}
SECRET_REFERENCE_RE = re.compile(r"\$\{\{\s*secrets\.[A-Za-z0-9_]+\s*}}|\b(?:process\.env|os\.environ)\.[A-Za-z0-9_]*(?:TOKEN|SECRET|API_KEY|PRIVATE_KEY)\b", re.I)
SECRET_TRANSMISSION_RE = re.compile(r"(?:curl|wget)\b[^\n]*(?:\$\{\{\s*secrets\.[A-Za-z0-9_]+\s*}}|\$[A-Z][A-Z0-9_]*(?:TOKEN|SECRET|API_KEY|PRIVATE_KEY)\b)", re.I)


def is_ci_or_deployment_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    return (".github" in parts and "workflows" in parts) or path.name.lower() in CI_FILENAMES


def scan_ci(root: Path, files: list[Path], texts: dict[Path, str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if not is_ci_or_deployment_path(path):
            continue
        text = texts.get(path, "")
        rel = relpath(path, root)
        transmitted = SECRET_TRANSMISSION_RE.search(text)
        if transmitted:
            findings.append(Finding(
                id="CI_SECRET_TRANSMISSION",
                severity="high",
                confidence="high",
                title="CI/deployment automation sends a secret-bearing value to an external command",
                file=rel,
                line=line_for_index(text, transmitted.start()),
                evidence="secret reference passed to network command",
                why_it_matters="CI credentials can be exfiltrated when a workflow sends them to an untrusted endpoint.",
                recommendation="Remove the transmission or restrict it to a reviewed, necessary endpoint with least-privilege credentials.",
                disposition="actionable",
            ))
            continue
        reference = SECRET_REFERENCE_RE.search(text)
        if reference:
            findings.append(Finding(
                id="CI_SECRET_REFERENCE",
                severity="medium",
                confidence="medium",
                title="CI/deployment automation references a secret-bearing environment value",
                file=rel,
                line=line_for_index(text, reference.start()),
                evidence="secret/environment reference",
                why_it_matters="Workflow credentials deserve review, but their presence does not establish MCP runtime credential exposure.",
                recommendation="Verify the credential is scoped to the intended CI/deployment operation and is not printed, copied, or transmitted.",
                disposition="review",
            ))
    return findings
