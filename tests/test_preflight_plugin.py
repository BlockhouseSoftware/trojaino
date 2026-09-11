"""Plugin workflow contract tests, separate from core scanner tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/trojaino'
CLI = PLUGIN / 'scripts/preflight.py'


class PluginWorkflowTests(unittest.TestCase):
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

    def test_automatic_intake_skill_and_startup_hook_are_registered(self):
        skill = (PLUGIN / 'skills/scan/SKILL.md').read_text()
        self.assertNotIn('disable-model-invocation: true', skill)
        hooks = json.loads((PLUGIN / 'hooks/hooks.json').read_text())['hooks']
        self.assertIn('SessionStart', hooks)
        handler = hooks['SessionStart'][0]['hooks'][0]
        self.assertEqual(handler['type'], 'command')
        self.assertFalse(handler.get('async', False))
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
            self.assertTrue((prepared / 'trojaino/preflight.py').is_file())
            hostile = Path(tmp) / 'candidate'
            hostile.mkdir()
            (hostile / 'trojaino.py').write_text("raise RuntimeError('untrusted import')")
            for event_name in ['SessionStart', 'PreToolUse']:
                handler = hooks[event_name][0]['hooks'][0]
                self.assertEqual(handler['command'], sys.executable)
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
