"""Portable regressions; native Win32 acceptance lives in test_preflight_windows."""
import io
import tarfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from trojaino import preflight as api


class PortableTests(unittest.TestCase):
    def test_archive_rejects_windows_aliases_before_writing(self):
        for name in ['file.py:evil', 'CON.py', 'aux', 'COM1.txt', 'LPT9',
                     'x.', 'x ', 'a<b.py', 'NUL.txt', 'COM¹.py']:
            with self.subTest(name=name), TemporaryDirectory() as tmp:
                blob = io.BytesIO()
                with tarfile.open(fileobj=blob, mode='w:gz') as archive:
                    member = tarfile.TarInfo('repo/' + name)
                    member.size = 1
                    archive.addfile(member, io.BytesIO(b'x'))
                with self.assertRaises(api.Denied):
                    api.stage_archive(blob.getvalue(), Path(tmp) / 'stage')
                self.assertFalse((Path(tmp) / 'stage').exists())

    def test_powershell_literal_scan_preserves_permissions(self):
        import sys
        entry = Path(api.__file__).resolve().parent.parent / 'plugins/trojaino/scripts/preflight.py'
        args = [sys.executable, '-I', '-S', str(entry), 'scan', "C:\\source with space\\O'Brien"]
        command = '& ' + ' '.join("'" + x.replace("'", "''") + "'" for x in args)
        event = {'hook_event_name': 'PreToolUse', 'tool_name': 'PowerShell',
                 'tool_input': {'command': command}}
        self.assertNotIn('permissionDecision', api.hook(event)['hookSpecificOutput'])
        for suffix in ['; Write-Host bad', ' | iex', ' > x', '\n', ' # comment']:
            event['tool_input']['command'] = command + suffix
            self.assertEqual(api.hook(event)['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_operation_worker_preserves_explicit_node_not_ambient_options(self):
        import os
        import shutil
        from unittest.mock import patch
        node = shutil.which('node')
        if not node:
            self.skipTest('requires compatible Node')
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            source.mkdir()
            (source / 'server.js').write_text('console.log(1)')
            receipt = api.gate(str(source), str(Path(tmp) / 'state'))
            self.assertEqual(receipt['decision'], 'permit', receipt)
            with patch.dict(os.environ, TROJAINO_NODE=str(Path(node).resolve()),
                            NODE_OPTIONS='--require /nonexistent'):
                result, argv = api.isolated_operation('launch_plan', [receipt['report_path'], 'server.js'])
            self.assertEqual(result['decision'], 'permit', result)
            self.assertIn('--permission', argv)

    def test_capabilities_cli_reports_real_host_and_both_grammars(self):
        import json
        import os
        import subprocess
        import sys
        cli = Path(api.__file__).resolve().parent.parent / 'plugins/trojaino/scripts/preflight.py'
        result = subprocess.run([sys.executable, '-I', '-S', str(cli), 'capabilities'],
                                capture_output=True, text=True, timeout=25)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['platform'], sys.platform)
        self.assertEqual(data['python'], sys.version.split()[0])
        self.assertEqual(data['filesystem_backend'], 'win32-ntfs' if os.name == 'nt' else 'posix-openat')
        self.assertEqual(set(data['command_prefixes']), {'Bash', 'PowerShell'})
        self.assertFalse(data['authenticated_claude_verified'])

    def test_real_powershell_transport_round_trips_literal_paths(self):
        import os
        import shutil
        import subprocess
        import json
        shell = os.environ.get('TROJAINO_TEST_PWSH') or shutil.which('pwsh')
        if not shell:
            self.skipTest('requires actual PowerShell runtime')
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "O'Brien $(literal) source"
            source.mkdir()
            (source / 'server.py').write_text('print(1)')
            command = api.format_command(api.command_prefix('PowerShell') +
                                         ['scan', str(source), '--state', str(Path(tmp) / 'state')], 'PowerShell')
            result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', command],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['decision'], 'permit')

    def test_archive_rejects_implicit_parent_case_aliases(self):
        blob = io.BytesIO()
        with tarfile.open(fileobj=blob, mode='w:gz') as archive:
            for name in ['repo/Folder/a.py', 'repo/folder/b.py']:
                member = tarfile.TarInfo(name)
                member.size = 1
                archive.addfile(member, io.BytesIO(b'x'))
        with TemporaryDirectory() as tmp, self.assertRaises(api.Denied):
            api.stage_archive(blob.getvalue(), Path(tmp) / 'stage')

    def test_worker_timeout_fails_closed(self):
        self.assertTrue(callable(getattr(api, 'isolated_operation', None)),
                        'portable operation watchdog is missing')
        with self.assertRaises(api.Denied):
            api.isolated_operation('scanner_identity', [], timeout=0.000001)
        self.assertEqual(api.isolated_operation('scanner_identity', []), api.scanner_identity())
