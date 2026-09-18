"""Verify Trojaino's reviewed self-scan baseline without suppressing findings."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

BASELINE_VERSION = 1
SHIPPED_SOURCE_PREFIXES = (
    ".claude-plugin/",
    "installer/",
    "plugins/",
    "requirements/",
    "scripts/",
    "schemas/",
    "trojaino/",
)
SHIPPED_SOURCE_FILES = {"pyproject.toml"}
FINDING_KEYS = ("id", "severity", "file", "line", "fingerprint")


def normalized_findings(report: dict[str, Any]) -> list[dict[str, Any]]:
    findings = report.get("findings")
    if not isinstance(findings, list):
        raise ValueError("self-scan report findings must be a list")
    normalized: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, dict) or any(key not in finding for key in FINDING_KEYS):
            raise ValueError("self-scan report finding is missing a required identity field")
        normalized.append({key: finding[key] for key in FINDING_KEYS})
    return sorted(normalized, key=lambda finding: tuple(str(finding[key]) for key in FINDING_KEYS))


def verify_report(report: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("profile") != "release" or baseline.get("profile") != "release":
        errors.append("self-scan and baseline must both use the release profile")
    if report.get("complete") is not True:
        errors.append("self-scan coverage was incomplete")
    if baseline.get("version") != BASELINE_VERSION:
        errors.append("unsupported self-scan baseline version")
    baseline_findings = baseline.get("findings")
    if not isinstance(baseline_findings, list) or any(
        not isinstance(finding, dict) or not isinstance(finding.get("review"), str) or not finding["review"].strip()
        for finding in baseline_findings
    ):
        errors.append("baseline findings require reviewed rationale")
    try:
        actual = normalized_findings(report)
        expected = normalized_findings(baseline)
    except ValueError as error:
        errors.append(str(error))
    else:
        if actual != expected:
            errors.append("unexpected or changed self-scan findings")
    return errors


def has_shipped_source_change(paths: list[str]) -> bool:
    return any(path in SHIPPED_SOURCE_FILES or path.startswith(SHIPPED_SOURCE_PREFIXES) for path in paths)


def changed_paths_from_git(root: Path, base_revision: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", base_revision, "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return [path for path in result.stdout.splitlines() if path]


def shipped_source_inventory(root: Path) -> list[dict[str, str]]:
    files: list[Path] = []
    for prefix in SHIPPED_SOURCE_PREFIXES:
        directory = root / prefix.rstrip("/")
        if directory.is_dir():
            files.extend(
                path for path in directory.rglob("*")
                if path.is_file()
                and not path.is_symlink()
                and "__pycache__" not in path.parts
                and path.suffix != ".pyc"
            )
    files.extend(root / name for name in SHIPPED_SOURCE_FILES if (root / name).is_file())
    return [
        {
            "file": path.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in sorted(set(files))
    ]


def has_shipped_source_symlink(root: Path) -> bool:
    return any(
        path.is_symlink()
        for prefix in SHIPPED_SOURCE_PREFIXES
        for path in (root / prefix.rstrip("/")).rglob("*")
        if (root / prefix.rstrip("/")).is_dir()
    )


def verify_source_inventory(root: Path, baseline: dict[str, Any]) -> list[str]:
    expected = baseline.get("source_inventory")
    if not isinstance(expected, list) or any(
        not isinstance(entry, dict) or set(entry) != {"file", "sha256"}
        for entry in expected
    ):
        return ["self-scan baseline source inventory is invalid"]
    if has_shipped_source_symlink(root):
        return ["reviewed shipped-source inventory changed"]
    if shipped_source_inventory(root) != sorted(expected, key=lambda entry: entry["file"]):
        return ["reviewed shipped-source inventory changed"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--changed-path", action="append", default=[])
    parser.add_argument("--changed-from", help="Git revision used to reject a baseline-only change")
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        changed_paths = args.changed_path
        if args.changed_from:
            changed_paths = changed_paths_from_git(args.root.resolve(), args.changed_from)
        errors = verify_report(report, baseline)
        errors.extend(verify_source_inventory(args.root.resolve(), baseline))
        if str(args.baseline).replace("\\", "/") in changed_paths and not has_shipped_source_change(changed_paths):
            errors.append("self-scan baseline changed without a shipped-source change")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors = [f"self-scan baseline verification could not run: {error}"]
    if errors:
        raise SystemExit("; ".join(errors))
    print("PASS reviewed release self-scan baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
