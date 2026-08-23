from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
import stat
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

from trojaino.file_utils import iter_files, read_bytes_no_symlink, relpath_for_issue
from trojaino.models import (
    CapabilityEvidence,
    Finding,
    PreflightEstimate,
    ScanIssue,
    ScanResult,
    SkippedFile,
    sort_findings,
    verdict_for,
    with_classified_context,
)
from trojaino.rules import RULES
from trojaino.rules.budget import BudgetedList, RuleBudget, RuleBudgetExceeded
from trojaino.rules.mcp import collect_capabilities


@dataclass(frozen=True)
class ScanLimits:
    """Resource ceilings for untrusted repository input."""

    max_files: int = 5_000
    max_entries: int = 20_000
    max_file_bytes: int = 1_000_000
    max_total_bytes: int = 20_000_000
    max_findings: int = 5_000
    max_report_bytes: int = 5_000_000
    max_depth: int = 50
    max_elapsed_seconds: float = 30.0

    def to_dict(self, preset: str = "custom") -> dict[str, int | float | str]:
        return {
            "preset": preset,
            "max_files": self.max_files,
            "max_entries": self.max_entries,
            "max_file_bytes": self.max_file_bytes,
            "max_total_bytes": self.max_total_bytes,
            "max_findings": self.max_findings,
            "max_report_bytes": self.max_report_bytes,
            "max_depth": self.max_depth,
            "max_elapsed_seconds": self.max_elapsed_seconds,
        }


BUDGET_PRESETS = {
    "standard": ScanLimits(),
    "large": ScanLimits(
        max_files=20_000,
        max_entries=100_000,
        max_file_bytes=5_000_000,
        max_total_bytes=100_000_000,
        max_findings=10_000,
        max_report_bytes=10_000_000,
        max_depth=75,
        max_elapsed_seconds=120.0,
    ),
    "exhaustive": ScanLimits(
        max_files=100_000,
        max_entries=500_000,
        max_file_bytes=20_000_000,
        max_total_bytes=500_000_000,
        max_findings=50_000,
        max_report_bytes=25_000_000,
        max_depth=100,
        max_elapsed_seconds=600.0,
    ),
}

MAX_SCAN_LIMITS = ScanLimits(
    max_files=1_000_000,
    max_entries=5_000_000,
    max_file_bytes=1_000_000_000,
    max_total_bytes=2_000_000_000,
    max_findings=100_000,
    max_report_bytes=100_000_000,
    max_depth=200,
    max_elapsed_seconds=3_600.0,
)


def limit_excesses(estimate: PreflightEstimate, limits: ScanLimits) -> list[str]:
    """Return limits that the metadata estimate already proves insufficient."""
    checks = (
        ("max_files", estimate.eligible_files, limits.max_files),
        ("max_entries", estimate.filesystem_entries, limits.max_entries),
        ("max_file_bytes", estimate.max_file_bytes, limits.max_file_bytes),
        ("max_total_bytes", estimate.total_bytes, limits.max_total_bytes),
        ("max_depth", estimate.max_depth, limits.max_depth),
    )
    return [name for name, estimated, allowed in checks if estimated > allowed]


def limits_for_estimate(estimate: PreflightEstimate, base: ScanLimits) -> ScanLimits:
    """Raise metadata limits with bounded headroom; runtime limits remain hard."""
    def headroom(value: int) -> int:
        return value + max(value // 10, 1)

    return replace(
        base,
        max_files=min(MAX_SCAN_LIMITS.max_files, max(base.max_files, headroom(estimate.eligible_files))),
        max_entries=min(MAX_SCAN_LIMITS.max_entries, max(base.max_entries, headroom(estimate.filesystem_entries))),
        max_file_bytes=min(MAX_SCAN_LIMITS.max_file_bytes, max(base.max_file_bytes, headroom(estimate.max_file_bytes))),
        max_total_bytes=min(MAX_SCAN_LIMITS.max_total_bytes, max(base.max_total_bytes, headroom(estimate.total_bytes))),
        max_depth=min(MAX_SCAN_LIMITS.max_depth, max(base.max_depth, estimate.max_depth)),
        max_elapsed_seconds=min(
            MAX_SCAN_LIMITS.max_elapsed_seconds,
            max(base.max_elapsed_seconds, BUDGET_PRESETS["large"].max_elapsed_seconds),
        ),
    )


_KNOWN_TOKEN_RE = re.compile(r"\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|SECRET|PRIVATE_KEY|PASSWORD)[A-Z0-9_]*\s*[:=]\s*)"
    r"(['\"]?)[A-Za-z0-9_./+=-]{12,}\2"
)
_BEARER_RE = re.compile(r"(?i)\b(authorization\s*:\s*bearer\s+)[^\s'\";|]+")
_URL_USERINFO_RE = re.compile(r"(?i)([a-z][a-z0-9+.-]{0,31}://)[^/@\s]+@")
_URL_SECRET_QUERY_RE = re.compile(
    r"(?i)([?&](?:access_token|api_key|apikey|token|secret|password)=)[^&#\s'\"]+"
)


def _bounded_redacted_evidence(value: str, limit: int = 240) -> str:
    """Keep report evidence useful without echoing secrets or hostile records."""
    upper_value = value.upper()
    private_key_start = upper_value.find("-----BEGIN ")
    if private_key_start >= 0 and "PRIVATE KEY-----" in upper_value[private_key_start:private_key_start + 100]:
        value = value[:private_key_start] + "[REDACTED PRIVATE KEY]"
    value = _KNOWN_TOKEN_RE.sub("[REDACTED TOKEN]", value)
    value = _SECRET_ASSIGNMENT_RE.sub(r"\1[REDACTED]", value)
    value = _BEARER_RE.sub(r"\1[REDACTED]", value)
    value = _URL_USERINFO_RE.sub(r"\1[REDACTED]@", value)
    value = _URL_SECRET_QUERY_RE.sub(r"\1[REDACTED]", value)
    value = " ".join(value.split())
    if len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def _safe_finding(finding: Finding) -> Finding:
    return replace(finding, evidence=_bounded_redacted_evidence(str(finding.evidence)))


def _safe_capability(capability: CapabilityEvidence) -> CapabilityEvidence:
    return replace(capability, evidence=_bounded_redacted_evidence(str(capability.evidence)))


def _add_issue_once(issues: list[ScanIssue], issue: ScanIssue) -> None:
    if not any(existing.code == issue.code and existing.file == issue.file for existing in issues):
        issues.append(issue)


def _json_report_size(result: ScanResult) -> int:
    rendered = json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=True)
    return len(rendered.encode("utf-8"))


def _enforce_report_budget(result: ScanResult, max_bytes: int) -> ScanResult:
    """Bound the canonical machine report and fail closed if data is omitted."""
    if _json_report_size(result) <= max_bytes:
        return result

    report_issue = ScanIssue(
        "report_size_limit",
        "Report details were truncated after the maximum serialized size was exceeded",
    )
    existing_issues = [issue for issue in result.issues or [] if issue.code != report_issue.code]
    bounded = replace(
        result,
        complete=False,
        verdict="DO NOT RUN",
        issues=[report_issue, *existing_issues],
    )

    def retain_largest_prefix(attribute: str, minimum: int = 0) -> None:
        nonlocal bounded
        original = list(getattr(bounded, attribute) or [])
        bounded = replace(bounded, **{attribute: original[:minimum]})
        if _json_report_size(bounded) > max_bytes:
            return
        low, high = minimum, len(original)
        while low < high:
            middle = (low + high + 1) // 2
            bounded = replace(bounded, **{attribute: original[:middle]})
            if _json_report_size(bounded) <= max_bytes:
                low = middle
            else:
                high = middle - 1
        bounded = replace(bounded, **{attribute: original[:low]})

    # Preserve findings and explicit coverage issues ahead of secondary detail.
    retain_largest_prefix("capabilities")
    retain_largest_prefix("skipped_files")
    retain_largest_prefix("findings")
    retain_largest_prefix("issues", minimum=1)
    if _json_report_size(bounded) > max_bytes:
        bounded = replace(bounded, recommended_command=None)
    if _json_report_size(bounded) > max_bytes and bounded.preflight:
        bounded = replace(bounded, preflight=replace(bounded.preflight, issues=[]))
    if _json_report_size(bounded) > max_bytes:
        bounded = replace(bounded, preflight=None, budget=None)
    if _json_report_size(bounded) > max_bytes:
        bounded = replace(bounded, target="[omitted: report size limit]")
    if _json_report_size(bounded) > max_bytes:
        bounded = replace(
            bounded,
            findings=[],
            capabilities=[],
            skipped_files=[],
            issues=[report_issue],
            preflight=None,
            budget=None,
            recommended_command=None,
            target="[omitted: report size limit]",
        )
    if _json_report_size(bounded) > max_bytes:
        raise ValueError("max_report_bytes is too small for the minimal canonical report")
    return bounded


def annotate_result(
    result: ScanResult,
    *,
    preflight: PreflightEstimate,
    limits: ScanLimits,
    budget_name: str,
    recommended_command: str | None,
) -> ScanResult:
    """Attach CLI planning metadata while preserving the report-size ceiling."""
    bounded_preflight = replace(preflight, issues=list(preflight.issues or [])[:10])
    annotated = replace(
        result,
        preflight=bounded_preflight,
        budget=limits.to_dict(budget_name),
        recommended_command=recommended_command,
    )
    return _enforce_report_budget(annotated, limits.max_report_bytes)


def scan_path(
    target: str | Path,
    profile: str = "default",
    *,
    limits: ScanLimits | None = None,
) -> ScanResult:
    limits = limits or ScanLimits()
    limit_values = (
        limits.max_files,
        limits.max_entries,
        limits.max_file_bytes,
        limits.max_total_bytes,
        limits.max_findings,
        limits.max_report_bytes,
        limits.max_depth,
        limits.max_elapsed_seconds,
    )
    try:
        invalid_limit = any(not math.isfinite(value) or value < 0 for value in limit_values)
    except (OverflowError, TypeError):
        invalid_limit = True
    if invalid_limit:
        raise ValueError("scan limits must be finite and non-negative")
    for field in (
        "max_files",
        "max_entries",
        "max_file_bytes",
        "max_total_bytes",
        "max_findings",
        "max_report_bytes",
        "max_depth",
        "max_elapsed_seconds",
    ):
        if getattr(limits, field) > getattr(MAX_SCAN_LIMITS, field):
            raise ValueError(f"{field} exceeds the supported hard ceiling")
    if limits.max_report_bytes < 4_096:
        raise ValueError("max_report_bytes must be at least 4096")

    started = time.monotonic()
    deadline = started + limits.max_elapsed_seconds
    root = Path(target).expanduser().absolute()
    issues: list[ScanIssue] = []
    skipped: list[SkippedFile] = []
    try:
        selected_info = root.stat(follow_symlinks=False)
    except OSError:
        selected_info = None
    selected_is_directory = selected_info is not None and stat.S_ISDIR(selected_info.st_mode)
    scan_root = root if selected_is_directory else root.parent
    expected_file_identity = (
        (selected_info.st_dev, selected_info.st_ino)
        if selected_info is not None and stat.S_ISREG(selected_info.st_mode)
        else None
    )
    try:
        scan_root_info = scan_root.stat(follow_symlinks=False)
        expected_root_identity = (scan_root_info.st_dev, scan_root_info.st_ino)
    except OSError:
        expected_root_identity = None
    files = iter_files(
        root,
        profile=profile,
        max_files=limits.max_files,
        max_entries=limits.max_entries,
        max_depth=limits.max_depth,
        deadline=deadline,
        issues=issues,
    )
    texts: dict[Path, str] = {}
    total_bytes = 0

    for index, path in enumerate(files):
        rel = relpath_for_issue(path, scan_root)
        if time.monotonic() >= deadline:
            _add_issue_once(issues, ScanIssue("elapsed_time_limit", "Elapsed scan-time limit was reached"))
            skipped.extend(
                SkippedFile(relpath_for_issue(remaining, scan_root), "elapsed_time_limit", "Not read before the scan deadline")
                for remaining in files[index:]
            )
            break
        data, status = read_bytes_no_symlink(
            path,
            scan_root,
            limits.max_file_bytes,
            expected_root_identity,
            expected_file_identity if path == root else None,
        )
        if status is not None:
            code = status if status in {"file_size_limit", "outside_root"} else "file_unreadable"
            message = {
                "file_size_limit": "File exceeded the per-file byte limit",
                "outside_root": "File resolution escaped the selected root",
            }.get(status, "File could not be safely read")
            _add_issue_once(issues, ScanIssue(code, message, rel))
            skipped.append(SkippedFile(rel, status, message))
            continue
        assert data is not None
        if total_bytes + len(data) > limits.max_total_bytes:
            _add_issue_once(issues, ScanIssue("total_bytes_limit", "Maximum aggregate input bytes were exceeded"))
            skipped.extend(
                SkippedFile(relpath_for_issue(remaining, scan_root), "total_bytes_limit", "Not read after aggregate byte limit")
                for remaining in files[index:]
            )
            break
        total_bytes += len(data)
        try:
            texts[path] = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            message = "File is not valid UTF-8 and was not partially decoded"
            _add_issue_once(issues, ScanIssue("invalid_utf8", message, rel))
            skipped.append(SkippedFile(rel, "invalid_utf8", message))

    findings: list[Finding] = []
    text_files = list(texts)
    rule_budget = RuleBudget(limits.max_findings, deadline)
    for rule in RULES:
        if time.monotonic() >= deadline:
            _add_issue_once(issues, ScanIssue("elapsed_time_limit", "Elapsed scan-time limit was reached"))
            break
        try:
            produced = rule(scan_root, text_files, texts, rule_budget)
        except RuleBudgetExceeded as exc:
            findings.extend(cast(list[Finding], exc.partial_items))
            message = (
                "Maximum finding count was exceeded"
                if exc.code == "finding_count_limit"
                else "Elapsed scan-time limit was reached"
            )
            _add_issue_once(issues, ScanIssue(exc.code, message))
            break
        except Exception as exc:  # A rule is an isolation boundary for hostile input.
            name = getattr(rule, "__name__", rule.__class__.__name__)
            _add_issue_once(issues, ScanIssue(
                "rule_failure",
                f"Rule {name} failed safely: {exc.__class__.__name__}",
            ))
            continue
        if not isinstance(produced, BudgetedList):
            remaining = limits.max_findings - len(findings)
            if len(produced) > remaining:
                findings.extend(produced[:max(remaining, 0)])
                _add_issue_once(issues, ScanIssue("finding_count_limit", "Maximum finding count was exceeded"))
                break
            rule_budget.remaining -= len(produced)
        findings.extend(produced)

    findings = sort_findings([
        with_classified_context(_safe_finding(finding)) for finding in findings
    ])
    for finding in findings:
        if finding.id in {"PKG_JSON_PARSE_ERROR", "PKG_JSON_INVALID_TYPE"}:
            _add_issue_once(issues, ScanIssue(
                "manifest_uninspectable",
                "Package manifest structure prevented complete lifecycle-script inspection",
                finding.file,
            ))
    capabilities: list[CapabilityEvidence] = []
    if time.monotonic() < deadline:
        try:
            produced_capabilities = collect_capabilities(
                scan_root,
                text_files,
                texts,
                RuleBudget(limits.max_findings, deadline),
            )
            capabilities = [_safe_capability(item) for item in produced_capabilities]
        except RuleBudgetExceeded as exc:
            capabilities = [
                _safe_capability(item)
                for item in cast(list[CapabilityEvidence], exc.partial_items)
            ]
            message = (
                "Maximum report-item count was exceeded"
                if exc.code == "finding_count_limit"
                else "Elapsed scan-time limit was reached"
            )
            _add_issue_once(issues, ScanIssue(exc.code, message))
        except Exception as exc:
            _add_issue_once(issues, ScanIssue(
                "rule_failure",
                f"Capability collection failed safely: {exc.__class__.__name__}",
            ))
    else:
        _add_issue_once(issues, ScanIssue("elapsed_time_limit", "Elapsed scan-time limit was reached"))

    complete = not issues
    verdict = "DO NOT RUN" if not complete else verdict_for(findings)
    result = ScanResult(
        target=str(root),
        verdict=verdict,
        findings=findings,
        files_scanned=len(texts),
        unreadable_files=len(skipped),
        capabilities=capabilities,
        profile=profile,
        complete=complete,
        issues=issues,
        skipped_files=skipped,
        scanned_at=datetime.now(timezone.utc).isoformat(),
    )
    return _enforce_report_budget(result, limits.max_report_bytes)
