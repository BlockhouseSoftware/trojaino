from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "build_windows_executable.py"
SPEC = importlib.util.spec_from_file_location("build_windows_executable", SCRIPT_PATH)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class WindowsExecutableBuildTests(unittest.TestCase):
    def test_windows_builder_invokes_pyinstaller_and_requires_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            distpath = root / "dist"
            workpath = root / "work"
            specpath = root / "spec"

            def create_expected_executable(command: list[str], **_: object) -> None:
                self.assertIn("--onedir", command)
                self.assertIn("--copy-metadata", command)
                self.assertIn("trojaino", command)
                executable = distpath / "tjscan" / "tjscan.exe"
                executable.parent.mkdir(parents=True)
                executable.touch()

            with patch.object(builder.sys, "platform", "win32"), patch.object(
                builder.subprocess, "run", side_effect=create_expected_executable
            ) as run:
                self.assertEqual(
                    builder.main(
                        [
                            "--distpath",
                            str(distpath),
                            "--workpath",
                            str(workpath),
                            "--specpath",
                            str(specpath),
                        ]
                    ),
                    0,
                )

            command = run.call_args.args[0]
            self.assertEqual(command[:3], [builder.sys.executable, "-m", "PyInstaller"])
            self.assertIn(str(builder.ENTRY_POINT), command)

    def test_builder_refuses_non_windows_hosts(self):
        with patch.object(builder.sys, "platform", "darwin"):
            with self.assertRaisesRegex(SystemExit, "must run on Windows"):
                builder.main([])


if __name__ == "__main__":
    unittest.main()
