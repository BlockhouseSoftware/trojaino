"""Explicit, privacy-preserving anonymous scan-statistics contributions.

This module deliberately builds an allowlisted summary from a completed scan.  It
never reads source files or uploads Trojaino's normal HTML/JSON reports.
"""
from __future__ import annotations

import json
import ssl
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import AbstractSet, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from trojaino import __version__
from trojaino.models import ScanResult
from trojaino.rules.registry import RULE_IDS

CONTRIBUTION_SCHEMA_VERSION = 1
MAX_CONTRIBUTION_BYTES = 64 * 1024
REQUEST_TIMEOUT_SECONDS = 10
# Set only in an official release after the hosted service, privacy notice, and
# deletion process exist. Keeping this unset means the local scanner can show a
# complete preview but cannot contact an arbitrary network destination.
OFFICIAL_CONTRIBUTION_ENDPOINT: str | None = "https://trojaino.llamaheads.com/v1/scan-statistics"
_ISSUE_CODES = {
    "elapsed_time_limit", "entry_count_limit", "file_count_limit", "file_size_limit", "file_unreadable",
    "finding_count_limit", "invalid_utf8", "manifest_uninspectable", "outside_root", "report_size_limit",
    "rule_contract_violation", "rule_failure", "total_bytes_limit",
}


class ContributionError(ValueError):
    """A local contribution could not be created or sent safely."""


@dataclass(frozen=True)
class ContributionReceipt:
    """One-time proof needed to later delete an anonymous contribution."""

    receipt_id: str
    deletion_token: str


def _count_records(records: list[dict[str, str]], *, fields: tuple[str, ...]) -> list[dict[str, str | int]]:
    counts = Counter(tuple(record[field] for field in fields) for record in records)
    return [
        {**dict(zip(fields, key, strict=True)), "count": count}
        for key, count in sorted(counts.items())
    ]


def _file_count_band(files_scanned: int) -> str:
    if files_scanned <= 10:
        return "0-10"
    if files_scanned <= 100:
        return "11-100"
    if files_scanned <= 1_000:
        return "101-1000"
    if files_scanned <= 10_000:
        return "1001-10000"
    return "10001+"


def _checked_string(value: object, *, field: str, allowed: AbstractSet[str]) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ContributionError(f"report has an unsupported {field}")
    return value


def _checked_identifier(value: object, *, field: str, allowed: AbstractSet[str]) -> str:
    """Accept only scanner-owned identifiers, never caller-controlled text."""
    if not isinstance(value, str) or value not in allowed:
        raise ContributionError(f"report has an unsupported {field}")
    return value


def _checked_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ContributionError(f"report has an invalid {field}")
    return value


def _checked_nonnegative_int(value: object, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ContributionError(f"report has an invalid {field}")
    return value


def _summary_from_report(report: dict[str, Any]) -> dict[str, Any]:
    """Extract only the allowlisted aggregate fields from a local report dict."""
    findings = report.get("findings")
    capabilities = report.get("capabilities")
    issues = report.get("issues")
    if not isinstance(findings, list) or not isinstance(capabilities, list) or not isinstance(issues, list):
        raise ContributionError("report is missing scan summaries")

    finding_records = []
    for finding in findings:
        if not isinstance(finding, dict):
            raise ContributionError("report contains an invalid finding")
        finding_records.append({
            "rule_id": _checked_identifier(finding.get("id"), field="finding rule id", allowed=RULE_IDS),
            "severity": _checked_string(finding.get("severity"), field="finding severity", allowed={"critical", "high", "medium", "low"}),
            "confidence": _checked_string(finding.get("confidence"), field="finding confidence", allowed={"high", "medium", "low"}),
            "context": _checked_string(finding.get("context"), field="finding context", allowed={
                "application_code", "test_code", "documentation", "agent_instruction", "mcp_or_tooling",
                "ci_or_deployment", "docker_config", "package_manifest", "environment_file", "unknown",
            }),
            "disposition": _checked_string(finding.get("disposition"), field="finding disposition", allowed={
                "actionable", "review", "likely_test_or_example", "likely_documentation_context",
            }),
        })

    capability_ids = []
    for capability in capabilities:
        if not isinstance(capability, dict):
            raise ContributionError("report contains an invalid capability summary")
        capability_ids.append(_checked_string(capability.get("id"), field="capability id", allowed={
            "shell_execution", "filesystem_read_write", "environment_credential_access",
            "outbound_network_access", "github_api_access",
        }))

    issue_codes = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise ContributionError("report contains an invalid scan issue")
        issue_codes.append(_checked_identifier(issue.get("code"), field="issue code", allowed=_ISSUE_CODES))

    scanner_version = report.get("scanner_version")
    if not isinstance(scanner_version, str) or not scanner_version or len(scanner_version) > 32:
        raise ContributionError("report has an invalid scanner version")

    return {
        "scanner_version": scanner_version,
        "profile": _checked_string(report.get("profile"), field="profile", allowed={"default", "release"}),
        "verdict": _checked_string(report.get("verdict"), field="verdict", allowed={"DO NOT RUN", "CAUTION", "NO CRITICAL RISKS FOUND"}),
        "complete": _checked_bool(report.get("complete"), field="complete"),
        "files_scanned_band": _file_count_band(_checked_nonnegative_int(report.get("files_scanned"), field="files scanned")),
        "findings": _count_records(finding_records, fields=("rule_id", "severity", "confidence", "context", "disposition")),
        "capability_counts": [
            {"capability_id": capability_id, "count": count}
            for capability_id, count in sorted(Counter(capability_ids).items())
        ],
        "issue_counts": [
            {"issue_code": issue_code, "count": count}
            for issue_code, count in sorted(Counter(issue_codes).items())
        ],
    }


def build_contribution_payload(result: ScanResult) -> dict[str, Any]:
    """Build the exact anonymous payload from a completed in-memory scan."""
    summary = _summary_from_report(result.to_dict())
    payload = {
        "schema_version": CONTRIBUTION_SCHEMA_VERSION,
        "contribution_id": str(uuid.uuid4()),
        **summary,
    }
    _ensure_payload_size(payload)
    return payload


def build_contribution_payload_from_report(report: dict[str, Any]) -> dict[str, Any]:
    """Build the same payload from a locally saved Trojaino JSON report."""
    payload = {
        "schema_version": CONTRIBUTION_SCHEMA_VERSION,
        "contribution_id": str(uuid.uuid4()),
        **_summary_from_report(report),
    }
    _ensure_payload_size(payload)
    return payload


def contribution_preview(payload: dict[str, Any]) -> str:
    """Return the exact compact JSON that would be sent, with no hidden fields."""
    _ensure_payload_size(payload)
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)


def _ensure_payload_size(payload: dict[str, Any]) -> bytes:
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=True).encode("utf-8")
    if len(encoded) > MAX_CONTRIBUTION_BYTES:
        raise ContributionError("anonymous contribution exceeds the 64 KB safety limit")
    return encoded


def submit_contribution(payload: dict[str, Any], endpoint: str | None = None) -> ContributionReceipt:
    """POST an allowlisted payload to a fixed HTTPS contribution endpoint.

    The endpoint is compiled into an official release rather than supplied by
    an end user, preventing Trojaino from becoming an SSRF client. Until the
    service and privacy controls are live, the endpoint remains unset and only
    the local preview is available.
    """
    if not OFFICIAL_CONTRIBUTION_ENDPOINT:
        raise ContributionError("anonymous sharing is not available until an official Trojaino service is configured")
    if endpoint is not None and endpoint != OFFICIAL_CONTRIBUTION_ENDPOINT:
        raise ContributionError("contribution endpoint is not an official Trojaino service")
    endpoint = OFFICIAL_CONTRIBUTION_ENDPOINT
    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ContributionError("contribution endpoint must be a clean HTTPS URL")
    request = Request(
        endpoint,
        data=_ensure_payload_size(payload),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": f"Trojaino/{__version__}"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS, context=ssl.create_default_context()) as response:
            if response.status not in {200, 201, 202}:
                raise ContributionError(f"contribution service returned HTTP {response.status}")
            response_body = response.read(4_096)
    except HTTPError as exc:
        raise ContributionError(f"contribution service returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise ContributionError("could not reach the contribution service") from exc

    try:
        response_data = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContributionError("contribution service returned an invalid response") from exc
    receipt_id = response_data.get("receipt_id") if isinstance(response_data, dict) else None
    deletion_token = response_data.get("deletion_token") if isinstance(response_data, dict) else None
    if not isinstance(receipt_id, str) or not receipt_id or len(receipt_id) > 128:
        raise ContributionError("contribution service did not return a valid receipt")
    if not isinstance(deletion_token, str) or not deletion_token or len(deletion_token) > 128:
        raise ContributionError("contribution service did not return a valid deletion token")
    return ContributionReceipt(receipt_id=receipt_id, deletion_token=deletion_token)


def delete_contribution(receipt_id: str, deletion_token: str) -> None:
    """Delete a prior anonymous contribution using its one-time receipt pair."""
    if not OFFICIAL_CONTRIBUTION_ENDPOINT:
        raise ContributionError("anonymous sharing is not available until an official Trojaino service is configured")
    if not isinstance(receipt_id, str) or not receipt_id or len(receipt_id) > 128:
        raise ContributionError("receipt must be a bounded string")
    if not isinstance(deletion_token, str) or not deletion_token or len(deletion_token) > 128:
        raise ContributionError("deletion token must be a bounded string")
    parsed = urlparse(OFFICIAL_CONTRIBUTION_ENDPOINT)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ContributionError("contribution endpoint must be a clean HTTPS URL")
    url = f"{OFFICIAL_CONTRIBUTION_ENDPOINT.rstrip('/')}/{receipt_id}"
    request = Request(
        url,
        data=json.dumps({"deletion_token": deletion_token}, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": f"Trojaino/{__version__}"},
        method="DELETE",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS, context=ssl.create_default_context()) as response:
            if response.status != 200:
                raise ContributionError(f"contribution service returned HTTP {response.status}")
            response_body = response.read(4_096)
    except HTTPError as exc:
        if exc.code == 404:
            raise ContributionError("receipt or deletion token was not found") from exc
        raise ContributionError(f"contribution service returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise ContributionError("could not reach the contribution service") from exc
    try:
        response_data = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContributionError("contribution service returned an invalid response") from exc
    if response_data != {"deleted": True}:
        raise ContributionError("contribution service did not confirm deletion")
