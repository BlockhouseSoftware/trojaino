#!/usr/bin/env python3
"""Verify the Trojaino wheel and sdist before a trusted PyPI publication."""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from pathlib import Path


class DistributionError(RuntimeError):
    """A release artifact violates the public distribution contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DistributionError(message)


def expected_artifacts(dist: Path, version: str) -> tuple[Path, Path]:
    wheels = sorted(dist.glob("*.whl"))
    sdists = sorted(dist.glob("*.tar.gz"))
    require(len(wheels) == 1, f"expected exactly one wheel in {dist}, found {len(wheels)}")
    require(len(sdists) == 1, f"expected exactly one sdist in {dist}, found {len(sdists)}")

    wheel, sdist = wheels[0], sdists[0]
    require(wheel.name.startswith(f"trojaino-{version}-"), f"wheel version does not match tag: {wheel.name}")
    require(sdist.name == f"trojaino-{version}.tar.gz", f"sdist version does not match tag: {sdist.name}")
    return wheel, sdist


def verify_wheel(wheel: Path, version: str) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        metadata_names = [name for name in names if name.endswith(".dist-info/METADATA")]
        require(len(metadata_names) == 1, "wheel must contain exactly one METADATA file")
        metadata = archive.read(metadata_names[0]).decode("utf-8")
        require(bool(re.search(rf"^Name: trojaino$", metadata, re.MULTILINE)), "wheel metadata name must be trojaino")
        require(bool(re.search(rf"^Version: {re.escape(version)}$", metadata, re.MULTILINE)), "wheel metadata version must match tag")
        require(
            bool(re.search(r"^License-Expression: AGPL-3\.0-only$", metadata, re.MULTILINE)),
            "wheel metadata must declare AGPL-3.0-only",
        )
        require(any(name.endswith(".dist-info/licenses/LICENSE") for name in names), "wheel must include LICENSE")
        require("trojaino/__init__.py" in names, "wheel must include the trojaino package")


def verify_sdist(sdist: Path, version: str) -> None:
    root = f"trojaino-{version}/"
    with tarfile.open(sdist, "r:gz") as archive:
        names = archive.getnames()
        require(f"{root}LICENSE" in names, "sdist must include LICENSE")
        require(f"{root}pyproject.toml" in names, "sdist must include pyproject.toml")
        require(f"{root}trojaino/__init__.py" in names, "sdist must include the trojaino package")
        require(f"{root}schemas/trojaino-report-v1.schema.json" in names, "sdist must include the report schema")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, required=True, help="directory containing built artifacts")
    parser.add_argument("--version", required=True, help="version derived from the immutable release tag")
    args = parser.parse_args()

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[a-z0-9.]+)?", args.version):
        parser.error("--version must be a normalized package version without the leading v")

    try:
        wheel, sdist = expected_artifacts(args.dist, args.version)
        verify_wheel(wheel, args.version)
        verify_sdist(sdist, args.version)
    except (DistributionError, OSError, tarfile.TarError, zipfile.BadZipFile) as error:
        print(f"distribution verification failed: {error}", file=sys.stderr)
        return 1

    print(f"verified {wheel.name} and {sdist.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
