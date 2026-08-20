from __future__ import annotations

from pathlib import Path

from trojaino.file_utils import iter_files, read_text
from trojaino.models import ScanResult, sort_findings, verdict_for, with_classified_context
from trojaino.rules import RULES
from trojaino.rules.mcp import collect_capabilities


def scan_path(target: str | Path, profile: str = "default") -> ScanResult:
    root = Path(target).expanduser().resolve()
    files = iter_files(root, profile=profile)
    texts = {}
    unreadable = 0
    for path in files:
        text = read_text(path)
        if text is None:
            unreadable += 1
            continue
        texts[path] = text
    scan_root = root if root.is_dir() else root.parent
    findings = []
    for rule in RULES:
        findings.extend(rule(scan_root, list(texts), texts))
    findings = sort_findings([with_classified_context(finding) for finding in findings])
    return ScanResult(
        target=str(root),
        verdict=verdict_for(findings),
        findings=findings,
        files_scanned=len(texts),
        unreadable_files=unreadable,
        capabilities=collect_capabilities(scan_root, list(texts), texts),
        profile=profile,
    )
