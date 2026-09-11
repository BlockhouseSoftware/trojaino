"""Trusted fixture setup, never canonicalize an untrusted gate input."""
from pathlib import Path
import tempfile


class TemporaryDirectory(tempfile.TemporaryDirectory):
    """Expand the trusted runner's TEMP alias before constructing test inputs.

    Keep tempfile's original cleanup target/finalizer; only expose the canonical
    spelling. Production locked_path must continue rejecting aliases.
    """
    def __enter__(self):
        return str(Path(super().__enter__()).resolve(strict=True))
