from __future__ import annotations

import importlib.util
import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "verify_distribution.py"
SPEC = importlib.util.spec_from_file_location("verify_distribution", SCRIPT)
assert SPEC and SPEC.loader
verify_distribution = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_distribution)


class DistributionVerificationTests(unittest.TestCase):
    version = "0.1.5"

    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="trojaino-distribution-"))
        self.dist = self.root / "dist"
        self.dist.mkdir()

    def write_wheel(self, *, include_license: bool = True) -> None:
        wheel = self.dist / f"trojaino-{self.version}-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("trojaino/__init__.py", "")
            archive.writestr(
                f"trojaino-{self.version}.dist-info/METADATA",
                f"Name: trojaino\nVersion: {self.version}\nLicense-Expression: AGPL-3.0-only\n",
            )
            if include_license:
                archive.writestr(f"trojaino-{self.version}.dist-info/licenses/LICENSE", "AGPL-3.0-only")

    def write_sdist(self) -> None:
        sdist = self.dist / f"trojaino-{self.version}.tar.gz"
        files = {
            "LICENSE": "AGPL-3.0-only",
            "pyproject.toml": "[project]",
            "trojaino/__init__.py": "",
            "schemas/trojaino-report-v1.schema.json": "{}",
        }
        with tarfile.open(sdist, "w:gz") as archive:
            for suffix, content in files.items():
                data = content.encode()
                info = tarfile.TarInfo(f"trojaino-{self.version}/{suffix}")
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))

    def test_valid_artifacts_pass_verification(self) -> None:
        self.write_wheel()
        self.write_sdist()

        wheel, sdist = verify_distribution.expected_artifacts(self.dist, self.version)
        verify_distribution.verify_wheel(wheel, self.version)
        verify_distribution.verify_sdist(sdist, self.version)

    def test_wheel_without_license_is_rejected(self) -> None:
        self.write_wheel(include_license=False)
        self.write_sdist()
        wheel, _ = verify_distribution.expected_artifacts(self.dist, self.version)

        with self.assertRaisesRegex(verify_distribution.DistributionError, "LICENSE"):
            verify_distribution.verify_wheel(wheel, self.version)


if __name__ == "__main__":
    unittest.main()
