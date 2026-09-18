"""Fixture canonicalization is separate from untrusted path validation."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from preflight_test_support import TemporaryDirectory
from trojaino import preflight as api


class FixtureTests(unittest.TestCase):
    def test_trusted_temporary_parent_alias_is_expanded(self):
        with tempfile.TemporaryDirectory() as outer:
            root = Path(outer).resolve()
            target = root / 'long temporary parent'
            target.mkdir()
            alias = root / 'alias'
            if os.name == 'nt':
                result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(alias), str(target)],
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
            else:
                alias.symlink_to(target, target_is_directory=True)
            try:
                with patch.object(tempfile, 'tempdir', str(alias)):
                    with TemporaryDirectory() as tmp:
                        self.assertEqual(Path(tmp), Path(tmp).resolve())
                        self.assertTrue(Path(tmp).is_dir())
                        source = Path(tmp) / 'source'
                        source.mkdir()
                        (source / 'server.py').write_text('print(1)')
                        state = Path(tmp) / 'state'
                        receipt = api.gate(str(source), str(state))
                        self.assertEqual(receipt['decision'], 'permit', receipt)
                        # Win32 must still reject an untrusted junction input;
                        # POSIX has a separate path policy and is not emulated.
                        if os.name == 'nt':
                            aliased_source = alias / Path(tmp).name / 'source'
                            self.assertEqual(api.gate(str(aliased_source), str(state))['decision'], 'deny')
                    self.assertFalse(Path(tmp).exists())
            finally:
                if os.name == 'nt':
                    os.rmdir(alias)

