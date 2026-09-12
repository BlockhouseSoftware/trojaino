"""Portable source packaging, never a prebuilt Windows executable claim."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from preflight_test_support import TemporaryDirectory
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class BundleTests(unittest.TestCase):
    def test_source_bundle_runs_without_checkout_or_installed_package(self):
        builder = ROOT / 'scripts/build_preflight_bundle.py'
        self.assertTrue(builder.is_file(), 'portable source builder missing')
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / 'bundle.zip'
            result = subprocess.run([sys.executable, str(builder), str(output)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertFalse(any('/.git/' in n or '/.venv/' in n or '__pycache__' in n for n in names))
                self.assertIn('trojaino-source/scripts/prepare_preflight_plugin.py', names)
                self.assertIn('trojaino-source/scripts/build_preflight_bundle.py', names)
                for document in ('sig-windows-trial.md', 'marketplace-lifecycle.md',
                                 'marketplace-requirements.md', 'marketplace-runtime-architecture.md',
                                 'personal-plugin-delivery.md', 'friendly-setup-architecture.md'):
                    self.assertIn('trojaino-source/docs/' + document, names)
                self.assertIn('trojaino-source/.claude-plugin/marketplace.json', names)
                manifest = json.loads(archive.read('trojaino-source/MANIFEST.sha256.json'))
                for name, digest in manifest.items():
                    self.assertEqual(hashlib.sha256(archive.read('trojaino-source/' + name)).hexdigest(), digest)
                archive.extractall(tmp)
            prepared = Path(tmp).resolve() / 'prepared'
            prepare = Path(tmp) / 'trojaino-source/scripts/prepare_preflight_plugin.py'
            result = subprocess.run([sys.executable, '-I', '-S', str(prepare), str(prepared)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            hooks = json.loads((prepared / 'plugins/trojaino/hooks/hooks.json').read_text())['hooks']
            handler = hooks['SessionStart'][0]['hooks'][0]
            result = subprocess.run([handler['command'], *handler['args']],
                                    input=json.dumps({'hook_event_name': 'SessionStart'}),
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['hookEventName'], 'SessionStart')
            cli = prepared / 'plugins/trojaino/scripts/preflight.py'
            source = Path(tmp) / 'candidate'
            source.mkdir()
            (source / 'server.py').write_text('print(1)')
            result = subprocess.run([sys.executable, '-I', '-S', str(cli), 'scan', str(source),
                                     '--state', str(Path(tmp) / 'state')], cwd=source,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, (result.args, result.stdout, result.stderr))
            self.assertEqual(json.loads(result.stdout)['decision'], 'permit')
