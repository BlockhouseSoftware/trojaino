"""Review blocker regressions; adversarial PowerShell is parsed, never run."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from trojaino import preflight as api


class PathBoundsTests(unittest.TestCase):
    def test_utf16_total_and_component_bounds(self):
        from trojaino.preflight_paths import windows_path, valid_component
        self.assertEqual(str(windows_path('C:\\' + '\U0001f600' * 118)), 'C:\\' + '\U0001f600' * 118)
        for value in ['C:\\' + '\U0001f600' * 119, 'C:\\' + '\U0001f600' * 150,
                      'C:\\a\\' + '\U0001f600' * 118, 'C:\\bad\ud800']:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                windows_path(value)
        self.assertTrue(valid_component('\U0001f600' * 127 + 'a'))
        self.assertFalse(valid_component('\U0001f600' * 128))
        self.assertFalse(valid_component('x' * 256))
        self.assertFalse(valid_component('\udfff'))


class QuoteTests(unittest.TestCase):
    def test_typographic_delimiters_denied(self):
        # PowerShell recognizes both curly single and double quote pairs.
        for quote in '\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f':
            args = api.command_prefix('PowerShell') + ['scan', 'C:\\intake\\x' + quote + '; Write-Output REVIEW_INJECTION; #']
            command = '& ' + ' '.join("'" + arg.replace("'", "''") + "'" for arg in args)
            with self.subTest(quote=hex(ord(quote))):
                self.assertEqual(api.hook({'hook_event_name': 'PreToolUse', 'tool_name': 'PowerShell',
                                          'tool_input': {'command': command}})['hookSpecificOutput'].get('permissionDecision'), 'deny')
                with self.assertRaises(api.Denied):
                    api.format_command(args, 'PowerShell')

    def test_real_parser_only_quote_oracle(self):
        shell = os.environ.get('TROJAINO_TEST_PWSH') or shutil.which('pwsh')
        if not shell:
            self.skipTest('requires actual PowerShell parser')
        parser = "$t=$null; $e=$null; $a=[System.Management.Automation.Language.Parser]::ParseInput($env:TROJAINO_PARSE_ONLY,[ref]$t,[ref]$e); @{statements=$a.EndBlock.Statements.Count; errors=@($e).Count} | ConvertTo-Json -Compress"
        for quote in '\u2018\u2019\u201a\u201b\u201c\u201d\u201e\u201f':
            args = api.command_prefix('PowerShell') + ['scan', 'C:\\intake\\x' + quote + '; Write-Output REVIEW_INJECTION; #']
            command = '& ' + ' '.join("'" + arg.replace("'", "''") + "'" for arg in args)
            result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', parser],
                                    env=dict(os.environ, POWERSHELL_TELEMETRY_OPTOUT='1', TROJAINO_PARSE_ONLY=command),
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            parsed = json.loads(result.stdout)
            print(json.dumps({'quote': hex(ord(quote)), 'parse_only': parsed}), flush=True)
            self.assertEqual(parsed, {'statements': 2 if quote <= '\u201b' else 1, 'errors': 0})
            self.assertEqual(api.hook({'hook_event_name': 'PreToolUse', 'tool_name': 'PowerShell',
                                      'tool_input': {'command': command}})['hookSpecificOutput'].get('permissionDecision'), 'deny')
