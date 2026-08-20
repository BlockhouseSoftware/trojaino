"""Trojaino local trust scanner."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib


def _package_version() -> str:
    """Read the project metadata when running from source, then installed metadata."""
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    if pyproject.is_file():
        with pyproject.open("rb") as source:
            return tomllib.load(source)["project"]["version"]
    try:
        return version("trojaino")
    except PackageNotFoundError:
        return "unknown"


__version__ = _package_version()
