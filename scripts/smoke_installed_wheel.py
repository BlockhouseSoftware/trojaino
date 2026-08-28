#!/usr/bin/env python3
"""Install a built Trojaino wheel in a fresh environment and smoke-test its CLI."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import venv
import zipfile


LICENSE_EXPRESSION = "AGPL-3.0-only"


def venv_python(environment: Path) -> Path:
    return environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def console_script(environment: Path) -> Path:
    return environment / ("Scripts/tjscan.exe" if os.name == "nt" else "bin/tjscan")


def validate_wheel_metadata(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        if len(metadata_names) != 1:
            raise RuntimeError("Wheel must contain exactly one distribution metadata file")
        metadata = archive.read(metadata_names[0]).decode("utf-8")
        if f"License-Expression: {LICENSE_EXPRESSION}" not in metadata:
            raise RuntimeError(f"Wheel metadata does not declare {LICENSE_EXPRESSION}")
        if not any(name.endswith(".dist-info/licenses/LICENSE") for name in names):
            raise RuntimeError("Wheel does not include the project LICENSE")


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode:
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        raise RuntimeError(f"Command failed ({completed.returncode}): {' '.join(command)}\n{output}")
    return completed


def assert_scan(command: list[str], expected_exit: int, expected_verdict: str) -> None:
    completed = subprocess.run(command, text=True, capture_output=True)
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    if completed.returncode != expected_exit:
        raise RuntimeError(
            f"Expected exit {expected_exit}, got {completed.returncode}: {' '.join(command)}\n{output}"
        )
    if expected_verdict not in output:
        raise RuntimeError(f"Expected verdict {expected_verdict!r}: {' '.join(command)}\n{output}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install a Trojaino wheel in a fresh venv and test the installed tjscan command."
    )
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--clean", type=Path, required=True)
    parser.add_argument("--risky", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    wheel = args.wheel.resolve()
    if not wheel.is_file():
        raise SystemExit(f"Wheel not found: {wheel}")
    validate_wheel_metadata(wheel)

    with tempfile.TemporaryDirectory(prefix="trojaino-wheel-smoke-") as temporary:
        environment = Path(temporary) / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = venv_python(environment)
        run_checked([
            str(python), "-m", "pip", "install", "--disable-pip-version-check",
            "--no-deps", "--no-index", str(wheel),
        ])
        scanner = console_script(environment)
        if not scanner.is_file():
            raise RuntimeError(f"Installed wheel did not expose tjscan at {scanner}")
        run_checked([str(scanner), "--help"])
        assert_scan([str(scanner), "scan", str(args.clean.resolve())], 0, "NO CRITICAL RISKS FOUND")
        assert_scan([str(scanner), "scan", str(args.risky.resolve())], 2, "DO NOT RUN")

    print(f"Installed-wheel smoke test passed for {wheel.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
