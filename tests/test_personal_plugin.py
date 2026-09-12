"""Final-location local plugin preparation; no real user configuration."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class PersonalPluginTests(unittest.TestCase):
    def test_readme_section_handles_crlf_and_rejects_changed_boundaries(self):
        import runpy
        helper = runpy.run_path(str(ROOT / 'scripts/prepare_preflight_plugin.py'))
        extract = helper['coverage_section']
        text = 'Intro\n## Coverage and security boundaries\nImportant limits.\n## Verification and rollout status\nOld setup.\n'
        self.assertEqual(extract(text.replace('\n', '\r\n')), 'Important limits.\n')
        for invalid in (text.replace('## Verification and rollout status', '## Verification status'),
                        text + '## Coverage and security boundaries\n',
                        text.replace('## Coverage and security boundaries', '## Limits')):
            with self.assertRaises(ValueError):
                extract(invalid)

    def test_identity_must_match_final_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp).resolve() / 'different-name'
            result = subprocess.run([sys.executable, '-I', '-S', str(ROOT / 'scripts/prepare_preflight_plugin.py'),
                str(destination), '--personal-plugin-name', 'trojaino-local-001'], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(destination.exists())

    def test_license_and_personal_instructions_are_packaged(self):
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp).resolve() / 'trojaino-local-001'
            result = subprocess.run([sys.executable, '-I', '-S', str(ROOT / 'scripts/prepare_preflight_plugin.py'),
                str(destination), '--personal-plugin-name', destination.name], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((destination / 'LICENSE').read_bytes(), (ROOT / 'LICENSE').read_bytes())
            for relative in ['README.md', 'skills/scan/SKILL.md']:
                text = (destination / relative).read_text()
                self.assertIn('/trojaino-local-001:scan', text)
                self.assertNotIn('/trojaino:scan', text)
                self.assertNotIn('../../docs/', text)
            hashes = json.loads((destination / 'MANIFEST.sha256.json').read_text())
            actual = {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in destination.rglob('*') if p.is_file() and p.name != 'MANIFEST.sha256.json'}
            self.assertEqual(hashes, actual)

    def test_final_layout_is_disabled_bound_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            destination = base / 'trojaino-local-001'
            command = [sys.executable, '-I', '-S', str(ROOT / 'scripts/prepare_preflight_plugin.py'),
                       str(destination), '--personal-plugin-name', 'trojaino-local-001']
            result = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((destination / '.claude-plugin/plugin.json').read_text())
            self.assertEqual(manifest['name'], 'trojaino-local-001')
            self.assertIs(manifest['defaultEnabled'], False)
            self.assertFalse((destination / 'plugins').exists())
            self.assertFalse((base / 'settings.json').exists())
            handler = json.loads((destination / 'hooks/hooks.json').read_text())['hooks']['SessionStart'][0]['hooks'][0]
            self.assertEqual(handler['args'][2], str(destination / 'scripts/preflight.py'))
            for advertised, expected in ((destination, 0), (base / 'copy', 2)):
                probe = subprocess.run([handler['command'], *handler['args']],
                    env=dict(os.environ, CLAUDE_PLUGIN_ROOT=str(advertised)),
                    input=json.dumps({'hook_event_name': 'SessionStart', 'source': 'startup'}),
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(probe.returncode, expected, probe.stdout + probe.stderr)
            before = {str(p.relative_to(destination)): p.read_bytes() for p in destination.rglob('*') if p.is_file()}
            again = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(before, {str(p.relative_to(destination)): p.read_bytes() for p in destination.rglob('*') if p.is_file()})

if __name__ == '__main__':
    unittest.main()
