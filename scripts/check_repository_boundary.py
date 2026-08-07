#!/usr/bin/env python3
"""Reject files that belong in AI Shield's internal or local-only workspaces."""
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
        print("Move these files to ../ai-shield-internal or ../../local as appropriate.")
        return 1
    print("Repository boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
