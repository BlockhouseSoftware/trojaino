#!/usr/bin/env python3
"""Build the Windows-only standalone tjscan executable with PyInstaller."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINT = REPOSITORY_ROOT / "trojaino" / "__main__.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a standalone Windows tjscan executable with PyInstaller."
    )
    parser.add_argument(
        "--distpath",
        type=Path,
        default=REPOSITORY_ROOT / "dist",
        help="Directory for the generated tjscan bundle.",
    )
    parser.add_argument(
        "--workpath",
        type=Path,
        default=REPOSITORY_ROOT / "build" / "pyinstaller",
        help="Temporary PyInstaller work directory.",
    )
    parser.add_argument(
        "--specpath",
        type=Path,
        default=REPOSITORY_ROOT / "build" / "pyinstaller-spec",
        help="Temporary PyInstaller spec directory.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if sys.platform != "win32":
        raise SystemExit("Windows executable builds must run on Windows.")

    for directory in (args.distpath, args.workpath, args.specpath):
        directory.mkdir(parents=True, exist_ok=True)

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        "tjscan",
        "--paths",
        str(REPOSITORY_ROOT),
        "--copy-metadata",
        "trojaino",
        "--distpath",
        str(args.distpath),
        "--workpath",
        str(args.workpath),
        "--specpath",
        str(args.specpath),
        str(ENTRY_POINT),
    ]
    subprocess.run(command, check=True, cwd=REPOSITORY_ROOT)

    executable = args.distpath / "tjscan" / "tjscan.exe"
    if not executable.is_file():
        raise SystemExit(f"PyInstaller did not produce the expected executable: {executable}")
    print(executable)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
