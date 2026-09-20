"""`tjscan setup` prepares a bound, disabled plugin without touching Claude settings."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

from trojaino.claude import prepare as prepare_module
from trojaino.claude import setup

IDENTITY = re.compile(r'trojaino-local-[a-z0-9]+(?:-[a-z0-9]+)*')
EXPECTED = {
    '.claude-plugin/plugin.json', 'LICENSE', 'MANIFEST.sha256.json', 'README.md',
    'hooks/hooks.json', 'scripts/preflight.py', 'skills/scan/SKILL.md',
}


class IdentityTests(unittest.TestCase):
    def test_identity_satisfies_the_preparation_contract(self):
        for version in ('0.2.0', '0.3.0-rc1', '1.10.2'):
            with self.subTest(version=version):
                self.assertRegex(setup.new_identity(version), IDENTITY)

    def test_identities_do_not_repeat(self):
        seen = {setup.new_identity('0.2.0') for _ in range(50)}
        self.assertEqual(len(seen), 50)

    def test_skills_directory_follows_claude_config_dir(self):
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': '/tmp/example-config'}):
            self.assertEqual(setup.skills_directory(), Path('/tmp/example-config/skills'))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(setup.skills_directory(), Path.home() / '.claude' / 'skills')


class SetupTests(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / 'skills'
            outcome = setup.run_setup('0.2.0', skills=skills, dry_run=True)
            self.assertFalse(outcome['written'])
            self.assertFalse(skills.exists(), 'dry run must not create the skills directory')

    def test_setup_writes_a_valid_disabled_bound_plugin(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / 'skills'
            outcome = setup.run_setup('0.2.0', skills=skills)
            plugin = Path(outcome['destination'])
            present = {str(p.relative_to(plugin)).replace('\\', '/')
                       for p in plugin.rglob('*') if p.is_file()}
            self.assertEqual(present, EXPECTED)

            manifest = json.loads((plugin / '.claude-plugin/plugin.json').read_text())
            self.assertEqual(manifest['name'], outcome['identity'])
            self.assertFalse(manifest['defaultEnabled'])

            hooks = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']
            self.assertEqual(sorted(hooks), ['PreToolUse', 'SessionStart'])
            for event in hooks.values():
                handler = event[0]['hooks'][0]
                self.assertEqual(handler['command'], str(Path(sys.executable).resolve()))
                self.assertTrue(Path(handler['args'][2]).is_absolute())

            skill = (plugin / 'skills/scan/SKILL.md').read_text()
            self.assertIn(f"/{outcome['identity']}:scan", skill)

    def test_repeated_setup_creates_a_distinct_identity_and_preserves_the_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / 'skills'
            first = setup.run_setup('0.2.0', skills=skills)
            before = (Path(first['destination']) / 'hooks/hooks.json').read_bytes()
            second = setup.run_setup('0.2.0', skills=skills)
            self.assertNotEqual(first['identity'], second['identity'])
            self.assertEqual((Path(first['destination']) / 'hooks/hooks.json').read_bytes(), before)
            self.assertIn(first['identity'], second['existing'])

    def test_setup_never_reuses_an_existing_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills = Path(tmp) / 'skills'
            outcome = setup.run_setup('0.2.0', skills=skills)
            with self.assertRaises(ValueError):
                prepare_module.prepare(outcome['destination'], outcome['identity'])


if __name__ == '__main__':
    unittest.main()
