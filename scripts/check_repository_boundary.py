#!/usr/bin/env python3
"""Reject files that belong in Trojaino's internal or local-only workspaces."""
from __future__ import annotations

import subprocess
from pathlib import Path

FORBIDDEN_TOP_LEVEL = {
    "internal",
    "local",
    "private",
    "reference",
    "reports",
    "strategy",
}
FORBIDDEN_COMPONENTS = {"raw-reports", "scan-reports"}
FORBIDDEN_SUFFIXES = {".key", ".numbers", ".pages", ".pptx"}
FORBIDDEN_NAMES = {".DS_Store"}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"], check=True, capture_output=True
    )
    return [item.decode() for item in result.stdout.split(b"\0") if item]


def line_ending_violations() -> list[str]:
    """Committed bytes must be LF on every platform.

    The sealed runtime image, the generated plugin directory and the release
    self-scan inventory are all verified byte for byte, so a CRLF blob would
    make those checks disagree across platforms about a file nobody edited.
    `.gitattributes` prevents it; this confirms the rule is still in force and
    that nothing slipped in before it was.
    """
    problems: list[str] = []
    attributes = Path(".gitattributes")
    if not attributes.is_file():
        problems.append(".gitattributes is missing; line endings are unpinned")
    elif "eol=lf" not in attributes.read_text(encoding="utf-8"):
        problems.append(".gitattributes no longer pins eol=lf")
    # -I skips blobs git considers binary, so images are not reported.
    found = subprocess.run(
        ["git", "grep", "-I", "-l", "-F", "\r", "HEAD"], capture_output=True
    )
    for line in found.stdout.decode("utf-8", "replace").splitlines():
        _, _, path = line.partition(":")
        if path:
            problems.append(f"{path}: committed with CRLF line endings")
    return problems


def violation_reason(path: str) -> str | None:
    parts = Path(path).parts
    if not parts:
        return None
    if parts[0].lower() in FORBIDDEN_TOP_LEVEL:
        return "forbidden top-level workspace path"
    if any(part.lower() in FORBIDDEN_COMPONENTS for part in parts):
        return "generated report directory"
    if Path(path).suffix.lower() in FORBIDDEN_SUFFIXES:
        return "internal document type"
    if Path(path).name in FORBIDDEN_NAMES:
        return "operating-system metadata"
    if Path(path).name.startswith("Screenshot "):
        return "uncurated screenshot"
    return None


def main() -> int:
    violations = [
        (path, reason)
        for path in tracked_files()
        if (reason := violation_reason(path)) is not None
    ]
    if violations:
        print("Repository boundary violations:")
        for path, reason in violations:
            print(f"- {path}: {reason}")
        print("Move these files to the adjacent internal workspace or ../../local as appropriate.")
        return 1
    endings = line_ending_violations()
    if endings:
        print("Line-ending violations:")
        for problem in endings:
            print(f"- {problem}")
        print("This repository is verified byte for byte; commit LF only.")
        return 1
    print("Repository boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
