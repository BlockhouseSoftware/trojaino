"""Actual approved-helper plan bytes; no candidate execution or activation."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'scripts/prepare_preflight_plugin.py'


class PreparationPlanTests(unittest.TestCase):
    def test_plan_requires_explicit_personal_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp).resolve() / 'unprepared'
            result = subprocess.run([sys.executable, '-I', '-S', str(HELPER), str(destination), '--plan'],
                                    capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0, 'planning legacy nonpersonal layout must refuse')
            self.assertIn(b'personal plugin identity required for planning', result.stderr)
            self.assertEqual(result.stdout, b'')
            self.assertFalse(destination.exists())

    def test_plan_errors_emit_no_archive_and_preserve_existing_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve()
            name = 'trojaino-local-plan-test'
            destination = parent / name
            destination.mkdir()
            marker = destination / 'keep.txt'
            marker.write_bytes(b'prior user bytes')
            for target, identity in ((destination, name), (parent / 'different', name),
                                     (parent / 'trojaino-local-invalid', 'invalid')):
                with self.subTest(target=target, identity=identity):
                    result = subprocess.run([sys.executable, '-I', '-S', str(HELPER), str(target),
                                             '--personal-plugin-name', identity, '--plan'],
                                            capture_output=True, timeout=30)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, b'')
                    self.assertEqual(marker.read_bytes(), b'prior user bytes')
                    self.assertEqual(set(parent.iterdir()), {destination})
                    self.assertEqual(set(destination.iterdir()), {marker})

    def test_plan_is_disabled_final_bound_and_byte_identical_without_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp).resolve()
            name = 'trojaino-local-plan-test'
            destination = parent / name
            hostile = parent / 'candidate'
            hostile.mkdir()
            (hostile / 'json.py').write_text('raise RuntimeError("candidate import forbidden")')
            (hostile / 'sitecustomize.py').write_text('raise RuntimeError("candidate import forbidden")')
            command = [sys.executable, '-I', '-S', str(HELPER), str(destination),
                       '--personal-plugin-name', name]
            env = dict(os.environ, PYTHONPATH=str(hostile))
            planned = subprocess.run([*command, '--plan'], capture_output=True, cwd=hostile, env=env, timeout=30)
            self.assertEqual(planned.returncode, 0, planned.stderr.decode(errors='replace'))
            self.assertFalse(destination.exists(), 'planning must not create final plugin')
            repeated = subprocess.run([*command, '--plan'], capture_output=True, cwd=hostile, env=env, timeout=30)
            self.assertEqual(repeated.returncode, 0, repeated.stderr.decode(errors='replace'))
            self.assertEqual(planned.stdout, repeated.stdout, 'deterministic rendered ZIP')
            with zipfile.ZipFile(io.BytesIO(planned.stdout)) as archive:
                payload = {entry.filename: archive.read(entry) for entry in archive.infolist()}
                self.assertEqual(len(payload), len(archive.infolist()), 'no duplicate entries')
                for entry in archive.infolist():
                    self.assertEqual(entry.date_time, (2020, 1, 1, 0, 0, 0))
                    self.assertEqual(entry.external_attr >> 16, 0o100644)
            manifest = json.loads(payload['.claude-plugin/plugin.json'])
            self.assertEqual(manifest['name'], name)
            self.assertIs(manifest['defaultEnabled'], False)
            hooks = json.loads(payload['hooks/hooks.json'])['hooks']['SessionStart'][0]['hooks'][0]
            self.assertEqual(hooks['command'], str(Path(sys.executable).resolve()))
            self.assertEqual(hooks['args'], ['-I', '-S', str(destination / 'scripts/preflight.py'), 'hook'])
            hashes = json.loads(payload['MANIFEST.sha256.json'])
            self.assertEqual(hashes, {key: hashlib.sha256(value).hexdigest() for key, value in payload.items()
                                      if key != 'MANIFEST.sha256.json'})
            prepared = subprocess.run(command, capture_output=True, cwd=hostile, env=env, timeout=30)
            self.assertEqual(prepared.returncode, 0, prepared.stderr.decode(errors='replace'))
            actual = {path.relative_to(destination).as_posix(): path.read_bytes()
                      for path in destination.rglob('*') if path.is_file()}
            self.assertEqual(payload, actual, 'every byte equals existing reviewed prepare behavior')


if __name__ == '__main__':
    unittest.main()
