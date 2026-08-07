from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aishield.report import render_html, render_json, render_text
from aishield.scanner import scan_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aishield",
        description="Local deterministic trust scanner for AI-built and downloaded software.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser(
        "scan",
        help="Scan a local file or folder",
        description="Scan a local project with deterministic rule packs. Exit codes: 0=no critical risks found, 1=caution, 2=do not run.",
    )
    scan.add_argument("target", help="File or folder to scan")
    scan.add_argument("--json", action="store_true", help="Print the full JSON report (not limited)")
    scan.add_argument("--html", help="Write a full HTML report to this path")
    scan.add_argument("--all", action="store_true", help="Show all findings in terminal output instead of the top 5")
    scan.add_argument(
        "--profile",
        choices=("default", "release"),
        default="default",
        help="Use release to scan shipped source while excluding tests, examples, and reference artifacts",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scan":
        target = Path(args.target).expanduser()
        if not target.exists():
            parser.error(f"target does not exist: {args.target}")
        result = scan_path(target, profile=args.profile)
        if args.html:
            Path(args.html).write_text(render_html(result), encoding="utf-8")
        finding_limit = None if args.all else 5
        print(render_json(result) if args.json else render_text(result, max_findings=finding_limit))
        return 2 if result.verdict == "DO NOT RUN" else 1 if result.verdict == "CAUTION" else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
