"""Model-free smoke assertions must detect no-op managers and mutating doctors."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import smoke_plugin_install as smoke


class ManagerStateTests(unittest.TestCase):
    def test_manager_state_requires_real_transition_and_preserves_unrelated(self):
        identity = 'trojaino@blockhouse-software'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'plugins').mkdir()
            registry = root / 'plugins/installed_plugins.json'
            settings = root / 'settings.json'
            unrelated = {'theme': 'dark', 'enabledPlugins': {'unrelated@fixture': False}}
            env = {'CLAUDE_CONFIG_DIR': tmp}
            for expected in (True, False, None):
                with self.subTest(expected=expected):
                    data = json.loads(json.dumps(unrelated))
                    entries = {identity: [{'scope': 'user'}]}
                    if expected is None:
                        entries = {}
                    else:
                        data['enabledPlugins'][identity] = expected
                    registry.write_text(json.dumps({'plugins': entries}))
                    settings.write_text(json.dumps(data))
                    smoke.check_manager_state(env, expected, unrelated)
                    # A success exit/message without the state transition is not enough.
                    data['enabledPlugins'][identity] = not expected
                    settings.write_text(json.dumps(data))
                    with self.assertRaises(AssertionError):
                        smoke.check_manager_state(env, expected, unrelated)
                    if expected is None:
                        data['enabledPlugins'].pop(identity)
                    else:
                        data['enabledPlugins'][identity] = expected
                    data['theme'] = 'light'
                    settings.write_text(json.dumps(data))
                    with self.assertRaises(AssertionError):
                        smoke.check_manager_state(env, expected, unrelated)

    def test_uninstall_rejects_residual_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'plugins').mkdir()
            (root / 'settings.json').write_text('{"enabledPlugins":{}}')
            (root / 'plugins/installed_plugins.json').write_text(json.dumps({
                'plugins': {'trojaino@blockhouse-software': [{'scope': 'user'}]}
            }))
            with self.assertRaises(AssertionError):
                smoke.check_manager_state({'CLAUDE_CONFIG_DIR': tmp}, None, {'enabledPlugins': {}})


class DoctorSmokeTests(unittest.TestCase):
    def test_doctor_preserves_exact_settings_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root / 'settings.json'
            settings.write_bytes(b'{"theme": "dark"}\n')
            env = {'CLAUDE_CONFIG_DIR': tmp}
            for status, code in [('Ready', 0), ('Needs attention', 1)]:
                with self.subTest(status=status):
                    result = subprocess.CompletedProcess([], code, json.dumps({'status': status}), '')
                    with patch.object(smoke, 'doctor_argv', return_value=['fixture']), patch.object(
                        smoke.subprocess, 'run', return_value=result
                    ):
                        self.assertEqual(smoke.check_doctor(root, env, status), {'status': status})

    def test_doctor_rejects_semantically_identical_settings_rewrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root / 'settings.json'
            settings.write_bytes(b'{}\n')
            def mutate(*args, **kwargs):
                settings.write_bytes(b'{ }\n')
                return subprocess.CompletedProcess([], 0, '{"status":"Ready"}', '')
            with patch.object(smoke, 'doctor_argv', return_value=['fixture']), patch.object(
                smoke.subprocess, 'run', side_effect=mutate
            ), self.assertRaisesRegex(AssertionError, 'settings'):
                smoke.check_doctor(root, {'CLAUDE_CONFIG_DIR': tmp}, 'Ready')

    def test_doctor_rejects_wrong_exit_or_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'settings.json').write_text('{}')
            for code, status in [(1, 'Ready'), (0, 'Needs attention')]:
                with self.subTest(code=code, status=status):
                    result = subprocess.CompletedProcess([], code, json.dumps({'status': status}), '')
                    with patch.object(smoke, 'doctor_argv', return_value=['fixture']), patch.object(
                        smoke.subprocess, 'run', return_value=result
                    ), self.assertRaises(AssertionError):
                        smoke.check_doctor(root, {'CLAUDE_CONFIG_DIR': tmp}, 'Ready')
