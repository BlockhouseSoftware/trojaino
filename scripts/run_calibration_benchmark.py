#!/usr/bin/env python3
"""Run the public synthetic Trojaino calibration corpus without executing it."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from trojaino import __version__
from trojaino.contract import REPORT_SCHEMA_VERSION, RULE_PACK_ID, RULE_PACK_VERSION
from trojaino.report import render_html, render_json
from trojaino.scanner import scan_path
DEFAULT_MANIFEST = REPOSITORY_ROOT / "benchmark" / "corpus" / "manifest.json"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "benchmark" / "artifacts"


def contained_path(relative_path: str) -> Path:
    candidate = (REPOSITORY_ROOT / relative_path).resolve()
    fixtures = (REPOSITORY_ROOT / "tests" / "fixtures").resolve()
    if fixtures not in (candidate, *candidate.parents):
        raise ValueError(f"benchmark target must stay under tests/fixtures: {relative_path}")
    if not candidate.is_dir():
        raise ValueError(f"benchmark target is not a directory: {relative_path}")
    return candidate


def result_summary(case: dict[str, str], result) -> dict:
    findings = [finding.to_dict() for finding in result.findings]
    return {
        "case_id": case["id"],
        "label": case["label"],
        "expected_verdict": case["expected_verdict"],
        "actual_verdict": result.verdict,
        "complete": result.complete,
        "finding_count": len(findings),
        "finding_ids": [finding["id"] for finding in findings],
        "findings": findings,
    }


def run(manifest_path: Path, output: Path) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1:
        raise ValueError("unsupported benchmark manifest format")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not 20 <= len(cases) <= 30:
        raise ValueError("benchmark manifest must contain 20–30 cases")
    case_ids = [case.get("id") for case in cases]
    if len(set(case_ids)) != len(case_ids) or any(not isinstance(case_id, str) for case_id in case_ids):
        raise ValueError("benchmark case IDs must be unique non-empty strings")

    shutil.rmtree(output, ignore_errors=True)
    output.mkdir(parents=True)
    summaries = []
    for case in cases:
        target = contained_path(case["path"])
        result = scan_path(target)
        if result.verdict != case["expected_verdict"]:
            raise ValueError(f"{case['id']}: expected {case['expected_verdict']}, got {result.verdict}")
        summary = result_summary(case, result)
        summaries.append(summary)
        (output / f"{case['id']}.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    aggregate = {
        "format_version": 1,
        "scanner_version": __version__,
        "schema_version": REPORT_SCHEMA_VERSION,
        "rule_pack": {"id": RULE_PACK_ID, "version": RULE_PACK_VERSION},
        "case_count": len(summaries),
        "cases_by_label": dict(sorted(Counter(item["label"] for item in summaries).items())),
        "cases_by_verdict": dict(sorted(Counter(item["actual_verdict"] for item in summaries).items())),
        "finding_burden_by_label": dict(sorted(
            (label, sum(item["finding_count"] for item in summaries if item["label"] == label))
            for label in {item["label"] for item in summaries}
        )),
        "cases": summaries,
        "limitations": [
            "All inputs are committed synthetic fixtures; results are not claims about third-party software.",
            "Detection rate is reported only for this labeled synthetic corpus, not as general recall.",
            "NO CRITICAL RISKS FOUND is not a safety certification.",
        ],
    }
    (output / "summary.json").write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    examples = {"clean-project": "clean-example", "bad-node-project": "finding-heavy-example"}
    for source, target_name in examples.items():
        case = next(item for item in cases if item["id"] == source)
        result = scan_path(contained_path(case["path"]))
        (output / f"{target_name}.json").write_text(render_json(result) + "\n", encoding="utf-8")
        (output / f"{target_name}.html").write_text(render_html(result), encoding="utf-8")
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    aggregate = run(args.manifest, args.output)
    print(f"calibrated {aggregate['case_count']} synthetic targets; verdicts: {aggregate['cases_by_verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
