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


@unittest.skipUnless(os.name == 'posix', 'preflight pilot requires POSIX')
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
        env = dict(os.environ, TROJAINO_PYTHON=sys.executable, CLAUDE_PLUGIN_ROOT=str(PLUGIN))
        result = subprocess.run(['/bin/sh', '-c', handler['command']],
                                env=env, input=json.dumps({'hook_event_name': 'SessionStart'}),
                                capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['hookSpecificOutput']['hookEventName'], 'SessionStart')


if __name__ == '__main__':
    unittest.main()
