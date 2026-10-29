"""Malformed local metadata must yield guidance, not a traceback or disclosure."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trojaino import __version__, doctor


class MalformedDoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='doctor-shape-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.config = self.base / 'config'
        self.root = self.base / 'plugin'
        self.root.mkdir()
        (self.config / 'plugins').mkdir(parents=True)
        self.registration = self.config / 'plugins/installed_plugins.json'
        self.settings = self.config / 'settings.json'
        self.registration.write_text(json.dumps({'plugins': {doctor.PLUGIN_ID: [
            {'installPath': str(self.root), 'version': __version__}]}}), encoding='utf-8')
        self.settings.write_text(json.dumps({'enabledPlugins': {doctor.PLUGIN_ID: True}}), encoding='utf-8')
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(self.config)}).start()
        # Do not inspect the developer's real ancestor settings during unit tests.
        real_read = doctor._read
        patch.object(doctor, '_read', side_effect=lambda path:
                     real_read(path) if path.is_relative_to(self.base) else {}).start()

    def assert_refusal_preserves_files(self):
        before = {p: p.read_bytes() for p in (self.registration, self.settings)}
        problems = doctor.inspect_registration(self.root, self.base)
        self.assertTrue(problems, 'malformed metadata must not appear ready')
        self.assertTrue(all(isinstance(p, str) for p in problems))
        self.assertNotIn('private-sentinel', json.dumps(problems))
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_malformed_settings_shapes(self):
        for value in ([], None, True, 1, 'private-sentinel',
                      {'enabledPlugins': []}, {'enabledPlugins': None}):
            with self.subTest(value=value):
                self.settings.write_text(json.dumps(value), encoding='utf-8')
                self.assert_refusal_preserves_files()

    def test_malformed_registration_shapes(self):
        for value in ({'plugins': None}, {'plugins': []},
                      {'plugins': {doctor.PLUGIN_ID: [None]}},
                      {'plugins': {doctor.PLUGIN_ID: ['private-sentinel']}},
                      {'plugins': {doctor.PLUGIN_ID: [{'installPath': 123}]}},
                      {'plugins': {doctor.PLUGIN_ID: {'installPath': 'private-sentinel'}}}):
            with self.subTest(value=value):
                self.registration.write_text(json.dumps(value), encoding='utf-8')
                self.assert_refusal_preserves_files()
