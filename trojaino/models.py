from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Literal

from trojaino import __version__

Severity = Literal["critical", "high", "medium", "low"]
Confidence = Literal["high", "medium", "low"]
Verdict = Literal["DO NOT RUN", "CAUTION", "NO CRITICAL RISKS FOUND"]
FindingContext = Literal[
    "application_code", "test_code", "documentation", "agent_instruction",
    "mcp_or_tooling", "ci_or_deployment", "docker_config", "package_manifest", "environment_file", "unknown",
]
Disposition = Literal[
    "actionable", "review", "likely_test_or_example", "likely_documentation_context",
]
CapabilityName = Literal[
    "shell_execution", "filesystem_read_write", "environment_credential_access",
    "outbound_network_access", "github_api_access",
]

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
DISPOSITION_RANK = {
    "actionable": 4,
    "review": 3,
    "likely_test_or_example": 2,
    "likely_documentation_context": 1,
}
TEST_EXAMPLE_PARTS = {"test", "tests", "spec", "fixture", "fixtures", "example", "examples", "sample", "mock", "mocks"}
AGENT_FILENAMES = {"agents.md", "claude.md", ".windsurfrules"}


@dataclass(frozen=True)
class Finding:
    id: str
    severity: Severity
    confidence: Confidence
    title: str
    file: str
    line: int | None
    evidence: str
    why_it_matters: str
    recommendation: str
    source: str = "deterministic"
    context: FindingContext = "unknown"
    disposition: Disposition = "review"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CapabilityEvidence:
    """A detected runtime capability, kept separate from vulnerability findings."""
    id: CapabilityName
    title: str
    file: str
    line: int | None
    rule: str
    evidence: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ScanIssue:
    """Machine-readable reason that a scan could not establish full coverage."""

    code: str
    message: str
    file: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SkippedFile:
    """A selected file that was deliberately not decoded or scanned."""

    file: str
    status: str
    detail: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PreflightEstimate:
    """Bounded metadata-only estimate of the work a scan may require."""

    eligible_files: int
    filesystem_entries: int
    total_bytes: int
    max_file_bytes: int
    max_depth: int
    symlinks: int = 0
    unreadable_entries: int = 0
    complete: bool = True
    issues: list[ScanIssue] | None = None

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["issues"] = [issue.to_dict() for issue in self.issues or []]
        return payload


def classify_context(file: str) -> FindingContext:
    """Classify a scanned path without changing a rule's security judgment."""
    path = PurePosixPath(file.replace("\\", "/"))
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    if name in AGENT_FILENAMES or ".cursor" in parts or "skills" in parts:
        return "agent_instruction"
    if name.startswith(".env"):
        return "environment_file"
    if ".github" in parts and "workflows" in parts:
        return "ci_or_deployment"
    if name in {".gitlab-ci.yml", ".gitlab-ci.yaml", "azure-pipelines.yml", "azure-pipelines.yaml"}:
        return "ci_or_deployment"
    if name in {"dockerfile", "docker-compose.yml", "docker-compose.yaml"} or path.suffix.lower() == ".dockerfile":
        return "docker_config"
    if name in {"package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml"}:
        return "package_manifest"
    if (
        parts & TEST_EXAMPLE_PARTS
        or ".test." in name
        or ".spec." in name
        or name.startswith(("test_", "tests_", "test-", "tests-"))
    ):
        return "test_code"
    # A generic tools/ directory is common in build systems and crypto test
    # generators. Reserve MCP/tooling context for explicit MCP/tooling paths.
    if "mcp" in parts or "tooling" in parts:
        return "mcp_or_tooling"
    if path.suffix.lower() in {".md", ".mdx", ".rst"}:
        return "documentation"
    if path.suffix.lower() in {".js", ".cjs", ".mjs", ".ts", ".tsx", ".jsx", ".py", ".sh"}:
        return "application_code"
    return "unknown"


def default_disposition(context: FindingContext) -> Disposition:
    if context == "test_code":
        return "likely_test_or_example"
    if context == "documentation":
        return "likely_documentation_context"
    return "review"


def with_classified_context(finding: Finding) -> Finding:
    """Add path-derived context without erasing a rule's explicit disposition."""
    context = classify_context(finding.file)
    disposition = finding.disposition
    if disposition == "review":
        disposition = default_disposition(context)
    return replace(finding, context=context, disposition=disposition)


@dataclass(frozen=True)
class ScanResult:
    target: str
    verdict: Verdict
    findings: list[Finding]
    files_scanned: int
    profile: str = "default"
    unreadable_files: int = 0
    capabilities: list[CapabilityEvidence] | None = None
    complete: bool = True
    issues: list[ScanIssue] | None = None
    skipped_files: list[SkippedFile] | None = None
    excluded_ds_store_files: int = 0
    preflight: PreflightEstimate | None = None
    budget: dict[str, int | float | str] | None = None
    recommended_command: str | None = None
    scanned_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "scanner_version": __version__,
            "target": self.target,
            "profile": self.profile,
            "verdict": self.verdict,
            "files_scanned": self.files_scanned,
            "unreadable_files": self.unreadable_files,
            "complete": self.complete,
            "status": "complete" if self.complete else "incomplete",
            "issues": [issue.to_dict() for issue in self.issues or []],
            "skipped_files": [skipped.to_dict() for skipped in self.skipped_files or []],
            "excluded_ds_store_files": self.excluded_ds_store_files,
            "findings": [finding.to_dict() for finding in self.findings],
            "capabilities": [capability.to_dict() for capability in self.capabilities or []],
            "preflight": self.preflight.to_dict() if self.preflight else None,
            "budget": self.budget,
            "recommended_command": self.recommended_command,
            "scanned_at": self.scanned_at,
        }


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(
        findings,
        key=lambda f: (-DISPOSITION_RANK[f.disposition], -SEVERITY_RANK[f.severity], f.file, f.line or 0, f.id),
    )


def verdict_for(findings: list[Finding]) -> Verdict:
    """Apply the alpha context/disposition contract without hiding dangerous exceptions."""
    do_not_run_ids = {
        "SECRET_KNOWN_TOKEN_PATTERN",
        "SECRET_ENV_FILE_COMMITTED",
        "PKG_REMOTE_LIFECYCLE_EXEC",
    }
    if any(f.id in do_not_run_ids for f in findings):
        return "DO NOT RUN"
    actionable = [f for f in findings if f.disposition == "actionable"]
    actionable_critical = sum(1 for f in actionable if f.severity == "critical")
    actionable_high = sum(1 for f in actionable if f.severity == "high")
    review_medium = sum(
        1 for f in findings
        if f.disposition == "review"
        and f.severity == "medium"
        and f.context in {"application_code", "mcp_or_tooling"}
    )
    if actionable_critical or actionable_high >= 2:
        return "DO NOT RUN"
    if actionable_high or review_medium >= 3:
        return "CAUTION"
    return "NO CRITICAL RISKS FOUND"


def relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
