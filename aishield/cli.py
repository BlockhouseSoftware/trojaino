from __future__ import annotations

import argparse
import json
import math
import shlex
import sys
from dataclasses import replace
from pathlib import Path

from aishield.file_utils import estimate_project
from aishield.report import render_html, render_json, render_text
from aishield.scanner import (
    BUDGET_PRESETS,
    MAX_SCAN_LIMITS,
    ScanLimits,
    annotate_result,
    limit_excesses,
    limits_for_estimate,
    scan_path,
)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be finite and greater than zero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="trojaino",
        description="Local deterministic install gate for AI tools and downloaded software.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "gui",
        help="Open the optional desktop scan window",
        description="Open Trojaino's optional desktop scan window. The CLI remains available for scripts and CI.",
    )
    share = sub.add_parser(
        "share",
        help="Preview or explicitly send anonymous scan statistics from a local JSON report",
        description="Build an allowlisted anonymous summary. It never uploads the report file, source code, paths, or evidence.",
    )
    share.add_argument("report", help="Local Trojaino JSON report to summarize")
    share.add_argument("--send", action="store_true", help="Explicitly send the previewed anonymous summary")
    unshare = sub.add_parser(
        "unshare",
        help="Delete a previously shared anonymous scan summary",
        description="Delete an anonymous summary using the receipt and deletion token shown when it was sent.",
    )
    unshare.add_argument("receipt", help="Receipt shown after the anonymous summary was sent")
    unshare.add_argument("deletion_token", help="One-time deletion token shown with the receipt")

    scan = sub.add_parser(
        "scan",
        help="Scan a local file or folder",
        description="Scan a local project with deterministic rule packs. Exit codes: 0=no critical risks found, 1=caution, 2=do not run.",
    )
    scan.add_argument("target", help="File or folder to scan")
    scan.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of the top-five terminal summary")
    scan.add_argument("--html", help="Write a full HTML report to this path")
    scan.add_argument("--all", action="store_true", help="Show all findings in terminal output instead of the top 5")
    scan.add_argument(
        "--profile",
        choices=("default", "release"),
        default="default",
        help="Use release to scan shipped source while excluding tests, examples, and reference artifacts",
    )
    scan.add_argument(
        "--budget",
        choices=tuple(BUDGET_PRESETS),
        default="standard",
        help="Resource preset: standard (default), large, or exhaustive",
    )
    scan.add_argument("--max-files", type=_positive_int, help="Override the selected preset's eligible-file limit")
    scan.add_argument("--max-entries", type=_positive_int, help="Override the filesystem-entry limit")
    scan.add_argument("--max-file-mb", type=_positive_float, help="Override the per-file limit in decimal MB")
    scan.add_argument("--max-total-mb", type=_positive_float, help="Override the aggregate-input limit in decimal MB")
    scan.add_argument("--max-findings", type=_positive_int, help="Override the finding-count limit")
    scan.add_argument("--max-report-mb", type=_positive_float, help="Override the canonical JSON report-data limit in decimal MB")
    scan.add_argument("--max-depth", type=_positive_int, help="Override the directory-depth limit")
    scan.add_argument("--max-seconds", type=_positive_float, help="Override the elapsed scan-time limit")
    scan.add_argument("--no-prompt", action="store_true", help="Never ask to raise a budget in an interactive terminal")
    return parser


def _limits_from_args(args: argparse.Namespace) -> tuple[ScanLimits, str]:
    limits = BUDGET_PRESETS[args.budget]
    overrides = {}
    mapping = {
        "max_files": args.max_files,
        "max_entries": args.max_entries,
        "max_findings": args.max_findings,
        "max_depth": args.max_depth,
        "max_elapsed_seconds": args.max_seconds,
    }
    overrides.update({key: value for key, value in mapping.items() if value is not None})
    for field, value in (
        ("max_file_bytes", args.max_file_mb),
        ("max_total_bytes", args.max_total_mb),
        ("max_report_bytes", args.max_report_mb),
    ):
        if value is not None:
            if value > getattr(MAX_SCAN_LIMITS, field) / 1_000_000:
                raise ValueError(f"--{field.replace('_bytes', '').replace('_', '-')} exceeds the supported hard ceiling")
            overrides[field] = int(value * 1_000_000)
    if overrides.get("max_report_bytes", limits.max_report_bytes) < 4_096:
        raise ValueError("--max-report-mb must allow at least 4096 bytes")
    selected = replace(limits, **overrides)
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
        if getattr(selected, field) > getattr(MAX_SCAN_LIMITS, field):
            raise ValueError(f"--{field.replace('_', '-')} exceeds the supported hard ceiling")
    return selected, args.budget if not overrides else f"{args.budget}+overrides"


def _format_bytes(value: int) -> str:
    if value < 1_000:
        return f"{value} bytes"
    if value < 1_000_000:
        return f"{value / 1_000:.1f} KB"
    return f"{value / 1_000_000:.1f} MB"


def _command_for_limits(target: Path, profile: str, limits: ScanLimits) -> str:
    prefix = f"trojaino scan {shlex.quote(str(target))} --profile {profile}"
    return " ".join((
        prefix,
        "--budget standard",
        f"--max-files {limits.max_files}",
        f"--max-entries {limits.max_entries}",
        f"--max-file-mb {math.ceil(limits.max_file_bytes / 1_000_000)}",
        f"--max-total-mb {math.ceil(limits.max_total_bytes / 1_000_000)}",
        f"--max-findings {limits.max_findings}",
        f"--max-report-mb {math.ceil(limits.max_report_bytes / 1_000_000)}",
        f"--max-depth {limits.max_depth}",
        f"--max-seconds {limits.max_elapsed_seconds:g}",
    ))


def _componentwise_max_limits(left: ScanLimits, right: ScanLimits) -> ScanLimits:
    fields = (
        "max_files",
        "max_entries",
        "max_file_bytes",
        "max_total_bytes",
        "max_findings",
        "max_report_bytes",
        "max_depth",
        "max_elapsed_seconds",
    )
    return replace(left, **{
        field: max(getattr(left, field), getattr(right, field))
        for field in fields
    })


def _runtime_recommendation(target: Path, profile: str, estimate, limits: ScanLimits, result) -> str | None:
    issue_codes = {issue.code for issue in result.issues or []}
    field_by_issue = {
        "file_count_limit": "max_files",
        "entry_count_limit": "max_entries",
        "file_size_limit": "max_file_bytes",
        "total_bytes_limit": "max_total_bytes",
        "finding_count_limit": "max_findings",
        "report_size_limit": "max_report_bytes",
        "depth_limit": "max_depth",
        "elapsed_time_limit": "max_elapsed_seconds",
    }
    relevant = issue_codes & set(field_by_issue)
    if not relevant:
        return None
    prefix = f"trojaino scan {shlex.quote(str(target))} --profile {profile}"
    relevant_fields = {field_by_issue[code] for code in relevant}
    for name in ("large", "exhaustive"):
        preset = BUDGET_PRESETS[name]
        candidate = _componentwise_max_limits(limits, preset)
        raises_relevant_limits = all(
            getattr(candidate, field) > getattr(limits, field)
            for field in relevant_fields
        )
        if raises_relevant_limits and (not estimate.complete or not limit_excesses(estimate, candidate)):
            return (
                f"{prefix} --budget {name}"
                if candidate == preset
                else _command_for_limits(target, profile, candidate)
            )
    candidate = limits_for_estimate(estimate, limits) if estimate.complete else limits
    overrides = {}
    for code in relevant:
        field = field_by_issue[code]
        current = getattr(candidate, field)
        overrides[field] = min(current * 2, getattr(MAX_SCAN_LIMITS, field))
    raised = replace(candidate, **overrides)
    if all(getattr(raised, field) <= getattr(limits, field) for field in relevant_fields):
        return None
    return _command_for_limits(target, profile, raised)


def _print_preflight(estimate, limits: ScanLimits, budget_name: str) -> None:
    status = "complete" if estimate.complete else "bounded/incomplete"
    print(
        f"Preflight ({status}): {estimate.eligible_files:,} eligible files, "
        f"{estimate.filesystem_entries:,} entries, {_format_bytes(estimate.total_bytes)} total, "
        f"largest file {_format_bytes(estimate.max_file_bytes)}."
    )
    if estimate.symlinks or estimate.unreadable_entries:
        print(f"Preflight warnings: {estimate.symlinks} symlinks, {estimate.unreadable_entries} unreadable entries.")
    excesses = limit_excesses(estimate, limits)
    if excesses:
        print(f"The {budget_name} budget is likely insufficient: {', '.join(excesses)}.")
    elif not estimate.complete:
        print("The bounded preflight did not finish, so budget fit cannot be determined.")
    else:
        print(f"The project fits the estimated metadata limits for the {budget_name} budget.")


def _choose_interactive_budget(estimate, limits: ScanLimits, budget_name: str) -> tuple[ScanLimits, str] | None:
    while True:
        excesses = limit_excesses(estimate, limits)
        if estimate.complete and not excesses:
            return limits, budget_name
        print("\nChoose how to continue:")
        print("  1. Run with the current budget (may be partial and will fail closed)")
        print("  2. Increase once to fit this estimate")
        print("  3. Use the large preset")
        print("  4. Use the exhaustive preset")
        print("  5. Cancel")
        try:
            choice = input("Selection [1-5]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if choice == "1":
            return limits, budget_name
        if choice == "2":
            if not estimate.complete:
                print("The preflight estimate is incomplete, so an exact fitted budget cannot be calculated.")
                continue
            fitted = limits_for_estimate(estimate, limits)
            if limit_excesses(estimate, fitted):
                print("This project exceeds the supported custom budget ceiling.")
                continue
            return fitted, "estimated-fit"
        if choice == "3":
            limits, budget_name = BUDGET_PRESETS["large"], "large"
        elif choice == "4":
            limits, budget_name = BUDGET_PRESETS["exhaustive"], "exhaustive"
        elif choice == "5":
            return None
        else:
            print("Enter a number from 1 to 5.")
            continue
        if limit_excesses(estimate, limits):
            print(f"The {budget_name} preset still does not fit the estimate.")
            continue
        if not estimate.complete:
            print("The preflight was incomplete; the selected preset remains a hard runtime ceiling.")
        return limits, budget_name


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "gui":
        from aishield.gui import launch_gui

        return launch_gui()
    if args.command == "unshare":
        from aishield.contributions import ContributionError, delete_contribution

        try:
            delete_contribution(args.receipt, args.deletion_token)
        except ContributionError as exc:
            print(f"Contribution was not deleted: {exc}", file=sys.stderr)
            return 1
        print("Anonymous statistics contribution deleted.")
        return 0
    if args.command == "share":
        from aishield.contributions import (
            ContributionError,
            build_contribution_payload_from_report,
            contribution_preview,
            submit_contribution,
        )

        report_path = Path(args.report).expanduser().absolute()
        try:
            if report_path.stat().st_size > 10_000_000:
                raise ContributionError("report exceeds the 10 MB local read limit")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise ContributionError("report must be a JSON object")
            payload = build_contribution_payload_from_report(report)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ContributionError) as exc:
            parser.error(f"could not prepare anonymous contribution: {exc}")
        print("Anonymous contribution preview (this is the complete payload):")
        print(contribution_preview(payload))
        if not args.send:
            print("Nothing was sent. Re-run with --send after reviewing this payload.")
            return 0
        try:
            receipt = submit_contribution(payload)
        except ContributionError as exc:
            print(f"Nothing was sent: {exc}", file=sys.stderr)
            return 1
        print("Anonymous statistics sent. Save both values to delete this contribution later:")
        print(f"Receipt: {receipt.receipt_id}")
        print(f"Deletion token: {receipt.deletion_token}")
        return 0
    if args.command == "scan":
        target = Path(args.target).expanduser().absolute()
        if not target.exists():
            parser.error(f"target does not exist: {args.target}")
        try:
            limits, budget_name = _limits_from_args(args)
        except ValueError as exc:
            parser.error(str(exc))
        estimate = estimate_project(target, profile=args.profile)
        excesses = limit_excesses(estimate, limits)
        interactive = (
            not args.json
            and not args.no_prompt
            and sys.stdin.isatty()
            and sys.stdout.isatty()
        )
        if interactive:
            _print_preflight(estimate, limits, budget_name)
            if excesses or not estimate.complete:
                selected = _choose_interactive_budget(estimate, limits, budget_name)
                if selected is None:
                    print("Scan cancelled before reading project files.")
                    return 2
                limits, budget_name = selected
        result = scan_path(target, profile=args.profile, limits=limits)
        result = annotate_result(
            result,
            preflight=estimate,
            limits=limits,
            budget_name=budget_name,
            recommended_command=None,
        )
        recommended_command = (
            None
            if result.complete
            else _runtime_recommendation(target, args.profile, estimate, limits, result)
        )
        if recommended_command:
            result = annotate_result(
                result,
                preflight=estimate,
                limits=limits,
                budget_name=budget_name,
                recommended_command=recommended_command,
            )
        if args.html:
            Path(args.html).write_text(render_html(result), encoding="utf-8")
        finding_limit = None if args.all else 5
        print(render_json(result) if args.json else render_text(result, max_findings=finding_limit))
        return 2 if result.verdict == "DO NOT RUN" else 1 if result.verdict == "CAUTION" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
