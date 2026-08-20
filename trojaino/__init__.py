"""Trojaino local trust scanner."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import sys
import tomllib


def _package_version() -> str:
    """Read bundled/source project metadata, then installed distribution metadata."""
    bundled_root = getattr(sys, "_MEIPASS", None)
    candidates = [
        Path(bundled_root) / "pyproject.toml" if bundled_root else None,
        Path(sys.executable).resolve().parent / "pyproject.toml",
        Path(__file__).resolve().parent.parent / "pyproject.toml",
    ]
    for pyproject in candidates:
        if pyproject and pyproject.is_file():
            with pyproject.open("rb") as source:
                return tomllib.load(source)["project"]["version"]
    try:
        return version("trojaino")
    except PackageNotFoundError:
        return "unknown"


__version__ = _package_version()
