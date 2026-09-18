"""Plugin workflow contract tests, separate from core scanner tests."""
import json
import os
import runpy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/trojaino'
CLI = PLUGIN / 'scripts/preflight.py'


class PluginWorkflowTests(unittest.TestCase):
    def test_binding_replacement_accepts_crlf_sealed_entry(self):
        helper = runpy.run_path(str(ROOT / 'scripts/prepare_preflight_plugin.py'))
        entry = CLI.read_bytes().replace(b'\r\n', b'\n').replace(b'\r', b'\n').replace(b'\n', b'\r\n')

        prepared = helper['bind_sealed_entry'](entry, ('C:/prepared/preflight.py', 'C:/Python/python.exe'))

        self.assertEqual(prepared.count(b'_EXPECTED_BINDING = '), 1)
        self.assertIn(b"_EXPECTED_BINDING = ('C:/prepared/preflight.py', 'C:/Python/python.exe')\r\n", prepared)

    def test_binding_replacement_rejects_mixed_newline_duplicate_slots(self):
        helper = runpy.run_path(str(ROOT / 'scripts/prepare_preflight_plugin.py'))
        entry = (b'_EXPECTED_BINDING = None\r\n'
                 b'_EXPECTED_BINDING = None\n')

        with self.assertRaises(ValueError):
            helper['bind_sealed_entry'](entry, ('C:/prepared/preflight.py', 'C:/Python/python.exe'))

    def test_session_start_supplies_trusted_scan_command(self):
        event = {'hook_event_name': 'SessionStart', 'source': 'startup'}
        result = subprocess.run([sys.executable, '-I', '-S', str(CLI), 'hook'],
                                input=json.dumps(event), capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)['hookSpecificOutput']
        self.assertEqual(output['hookEventName'], 'SessionStart')
        self.assertNotIn('permissionDecision', output)
        self.assertIn(sys.executable, output['additionalContext'])
        self.assertIn(str(CLI), output['additionalContext'])
        self.assertIn('before', output['additionalContext'])
        self.assertNotIn('trojaino:scan', output['additionalContext'],
                         'SessionStart must not direct renamed personal plugins to a missing skill')
        self.assertIn("this plugin's scan skill", output['additionalContext'])

    def test_prepared_hook_template_rejects_symlinked_interpreter(self):
        helper = runpy.run_path(str(ROOT / 'scripts/prepare_preflight_plugin.py'))
        with tempfile.TemporaryDirectory() as tmp:
            linked_python = Path(tmp) / 'python'
            linked_python.symlink_to(sys.executable)
            with self.assertRaises(ValueError):
                helper['prepared_hook_manifest'](str(linked_python), PLUGIN)

    def test_moved_prepared_entry_is_denied(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            destination = root / 'prepared'
            helper = ROOT / 'scripts/prepare_preflight_plugin.py'
            result = subprocess.run([sys.executable, '-I', '-S', str(helper), str(destination)],
                                    text=True, capture_output=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            moved = root / 'moved'
            shutil.move(str(destination), moved)
            entry = moved / 'plugins/trojaino/scripts/preflight.py'
            result = subprocess.run([sys.executable, '-I', '-S', str(entry), 'capabilities'],
                                    text=True, capture_output=True, timeout=25)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn('prepared_binding_mismatch', result.stdout)

    def test_copied_hooks_cannot_invoke_original_prepared_runtime(self):
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            prepared = root / 'prepared'
            result = subprocess.run([sys.executable, '-I', '-S',
                str(ROOT / 'scripts/prepare_preflight_plugin.py'), str(prepared)],
                capture_output=True, text=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            plugin = prepared / 'plugins/trojaino'
            copied = root / 'cached-copy'
            shutil.copytree(plugin, copied)
            handler = json.loads((copied / 'hooks/hooks.json').read_text())['hooks']['SessionStart'][0]['hooks'][0]
            for advertised_root, expected in ((str(plugin), 0), (str(copied), 2)):
                result = subprocess.run([handler['command'], *handler['args']],
                    env=dict(os.environ, CLAUDE_PLUGIN_ROOT=advertised_root),
                    input=json.dumps({'hook_event_name': 'SessionStart', 'source': 'startup'}),
                    capture_output=True, text=True, timeout=25)
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                if expected:
                    self.assertIn('prepared_plugin_root_mismatch', result.stdout)

    def test_preparation_adds_literal_trusted_hooks_to_a_new_private_copy(self):
        skill = (PLUGIN / 'skills/scan/SKILL.md').read_text()
        self.assertNotIn('disable-model-invocation: true', skill)
        hooks = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks']
        self.assertEqual(hooks, {})
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            prepared = Path(tmp).resolve() / "private prepared O'Brien"
            helper = ROOT / 'scripts/prepare_preflight_plugin.py'
            self.assertTrue(helper.is_file(), 'private plugin preparation helper required')
            result = subprocess.run([sys.executable, '-I', '-S', str(helper), str(prepared)],
                                    capture_output=True, text=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            plugin = prepared / 'plugins/trojaino'
            hooks = json.loads((plugin / 'hooks/hooks.json').read_text())['hooks']
            if os.name == 'posix':
                self.assertEqual((plugin / 'hooks/hooks.json').stat().st_mode & 0o077, 0)
                self.assertEqual((plugin / 'scripts/preflight.py').stat().st_mode & 0o077, 0)
            self.assertTrue((prepared / 'trojaino/preflight.py').is_file())
            hostile = Path(tmp) / 'candidate'
            hostile.mkdir()
            (hostile / 'trojaino.py').write_text("raise RuntimeError('untrusted import')")
            for event_name in ['SessionStart', 'PreToolUse']:
                handler = hooks[event_name][0]['hooks'][0]
                self.assertEqual(handler['command'], str(Path(sys.executable).resolve()))
                self.assertEqual(handler['args'], ['-I', '-S', str(plugin / 'scripts/preflight.py'), 'hook'])
                self.assertFalse(handler.get('async', False))
                # Execute the generated manifest exactly, no interpreter substitution.
                result = subprocess.run([handler['command'], *handler['args']], cwd=hostile,
                                        env=dict(os.environ, PYTHONPATH=str(hostile), TROJAINO_PYTHON='/not/an/interpreter'),
                                        input=json.dumps({'hook_event_name': event_name, 'tool_name': 'Bash',
                                                          'tool_input': {'command': 'npm install'}}),
                                        capture_output=True, text=True, timeout=25)
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)['hookSpecificOutput']
                self.assertEqual(output['hookEventName'], event_name)
                if event_name == 'SessionStart':
                    from trojaino.preflight import format_command
                    tool = 'PowerShell' if os.name == 'nt' else 'Bash'
                    self.assertIn(format_command([handler['command'], *handler['args'][:-1]], tool), output['additionalContext'])
                    self.assertNotIn('permissionDecision', output)
                else:
                    self.assertEqual(output['permissionDecision'], 'deny')
            again = subprocess.run([sys.executable, '-I', '-S', str(helper), str(prepared)],
                                   capture_output=True, text=True, timeout=25)
            self.assertNotEqual(again.returncode, 0)


if __name__ == '__main__':
    unittest.main()
