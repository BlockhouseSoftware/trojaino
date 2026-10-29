"""Doctor must not execute hook commands from a damaged plugin package."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from trojaino.claude.payload import marketplace_files
from trojaino import doctor


class DoctorIntegrityGateTests(unittest.TestCase):
    def test_malformed_inventory_does_not_crash_or_execute_hooks(self):
        with tempfile.TemporaryDirectory(prefix='doctor-inventory-') as tmp:
            root = Path(tmp)
            from trojaino import __version__
            (root / 'integrity.json').write_text(json.dumps({'version': __version__, 'files': []}))
            with patch.object(doctor, 'inspect_registration', return_value=[]), \
                 patch.object(doctor.subprocess, 'run', return_value=subprocess.CompletedProcess(
                     [], 0, '2.1.274 (Claude Code)', '')) as run:
                result = doctor.check(str(root / 'scripts/preflight.py'))
            self.assertEqual(result['status'], 'Needs attention')
            self.assertEqual(run.call_count, 1)
            self.assertTrue(any('integrity' in action for action in result['actions']))

    def test_damaged_payload_is_not_executed(self):
        with tempfile.TemporaryDirectory(prefix='doctor-integrity-') as tmp:
            root = Path(tmp)
            for name, data in marketplace_files().items():
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            hooks_path = root / 'hooks/hooks.json'
            hooks = json.loads(hooks_path.read_text())
            hooks['hooks']['SessionStart'][0]['hooks'][0]['command'] = 'untrusted-private-sentinel'
            hooks_path.write_text(json.dumps(hooks))
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
            # Never execute the tampered command. The subprocess spy exposes any
            # attempted invocation while the CLI version probe remains harmless.
            with patch.object(doctor, 'inspect_registration', return_value=[]), \
                 patch.object(doctor.subprocess, 'run', return_value=subprocess.CompletedProcess(
                     [], 0, '2.1.274 (Claude Code)', '')) as run:
                result = doctor.check(str(root / 'scripts/preflight.py'))
            self.assertEqual(result['status'], 'Needs attention')
            self.assertTrue(any(c['check'] == 'Packaged file integrity' and not c['ok']
                                for c in result['checks']))
            self.assertEqual(run.call_count, 1, 'only the Claude version probe may run after integrity failure')
            self.assertTrue(any(c['check'] == 'Hook execution' and not c['ok']
                                for c in result['checks']))
            self.assertNotIn('untrusted-private-sentinel', json.dumps(result))
            self.assertEqual({p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}, before)
