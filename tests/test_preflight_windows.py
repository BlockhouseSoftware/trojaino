"""Real Win32 acceptance. Skipped, never simulated, on other hosts."""
import json
import os
from pathlib import Path
import subprocess
import sys
from preflight_test_support import TemporaryDirectory
import time
import unittest
from trojaino import preflight as api

CLI = Path(__file__).resolve().parents[1] / 'plugins/trojaino/scripts/preflight.py'


@unittest.skipUnless(os.name == 'nt', 'requires actual native Windows')
class WindowsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(TemporaryDirectory()))
        self.source = self.root / "source with space"
        self.source.mkdir()
        (self.source / 'server.py').write_text('print("hello")\n')
        self.state = self.root / 'state'
        # Surface Win32 path errors directly instead of only gate's safe denial.
        from trojaino.preflight_windows import locked_path
        with locked_path(self.source):
            pass

    def assert_clean_gate(self):
        # A denial fixture must first prove it reaches the real scan boundary.
        receipt = api.gate(str(self.source), str(self.state))
        self.assertEqual(receipt['decision'], 'permit', (str(self.root), receipt))

    def test_real_scan_receipt_and_python_launch(self):
        receipt = api.gate(str(self.source), str(self.state))
        self.assertEqual(receipt['decision'], 'permit', receipt)
        self.assertEqual(api.verify(receipt['report_path'])['decision'], 'permit')
        from preflight_test_support import sealed_gate
        sealed_receipt = sealed_gate(self.source, self.state)
        self.assertEqual(sealed_receipt['decision'], 'permit', sealed_receipt)
        result = subprocess.run([sys.executable, '-I', '-S', str(CLI), 'launch',
                                 sealed_receipt['report_path'], '--entry', 'server.py'],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'hello\n')
        (Path(receipt['staged_path']) / 'server.py').write_text('print(2)')
        self.assertEqual(api.verify(receipt['report_path'])['decision'], 'deny')

    def test_ads_on_file_and_directory_denied(self):
        self.assert_clean_gate()
        for target in [self.source / 'server.py', self.source]:
            with self.subTest(target=target):
                stream = str(target) + ':hidden'
                with open(stream, 'wb') as output:
                    output.write(b'hidden')
                try:
                    self.assertEqual(api.gate(str(self.source), str(self.state))['decision'], 'deny')
                finally:
                    os.unlink(stream)

    def test_junction_source_ancestor_and_state_denied(self):
        self.assert_clean_gate()
        link = self.root / 'junction'
        result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(self.source)],
                                capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        try:
            self.assertEqual(api.gate(str(link), str(self.state))['decision'], 'deny')
            child = self.source / 'child'
            child.mkdir()
            (child / 'server.py').write_text('print(1)')
            self.assertEqual(api.gate(str(link / 'child'), str(self.state))['decision'], 'deny')
            self.assertEqual(api.gate(str(self.source), str(link / 'state'))['decision'], 'deny')
        finally:
            os.rmdir(link)

    def test_hardlink_denied(self):
        self.assert_clean_gate()
        os.link(self.source / 'server.py', self.source / 'alias.py')
        self.assertEqual(api.gate(str(self.source), str(self.state))['decision'], 'deny')

    def test_snapshot_holds_file_against_write_and_rename(self):
        from trojaino.preflight_windows import locked_path
        file = self.source / 'server.py'
        with locked_path(file, directory=False):
            with self.assertRaises(OSError):
                file.write_text('changed')
            with self.assertRaises(OSError):
                file.rename(self.source / 'moved.py')
        file.write_text('after release')

    def test_blocked_hook_stdin_times_out_with_deny(self):
        process = subprocess.Popen([sys.executable, '-I', '-S', str(CLI), 'hook'],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            process.wait(timeout=25)  # intentionally never close/write stdin
            self.assertEqual(json.loads(process.stdout.read())['hookSpecificOutput']['permissionDecision'], 'deny')
        finally:
            process.kill() if process.poll() is None else None
            process.communicate(timeout=5)

    def test_private_job_dacl_has_no_inherited_or_broad_access(self):
        from trojaino.preflight_windows import private_job, current_user_sid
        import shutil
        shell = shutil.which('pwsh.exe') or shutil.which('powershell.exe')
        self.assertIsNotNone(shell)
        with private_job(str(self.state)) as job:
            literal = "'" + str(job).replace("'", "''") + "'"
            # Get-Acl.Sddl can abbreviate the numeric RID-500 SID as LA.
            # Ask .NET for explicit AND inherited rules as SecurityIdentifiers;
            # do not accept an alias or a localized account display name.
            command = (
                "$ErrorActionPreference='Stop'; $acl=Get-Acl -LiteralPath " + literal + "; "
                "$rules=@($acl.GetAccessRules($true,$true,"
                "[System.Security.Principal.SecurityIdentifier]) | ForEach-Object { "
                "@{sid=$_.IdentityReference.Value; type=[int]$_.AccessControlType; "
                "rights=[int]$_.FileSystemRights; inherited=$_.IsInherited; "
                "inheritance=[int]$_.InheritanceFlags; propagation=[int]$_.PropagationFlags} }); "
                "@{protected=$acl.AreAccessRulesProtected; rules=$rules; sddl=$acl.Sddl} "
                "| ConvertTo-Json -Depth 4 -Compress"
            )
            result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', command],
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            from preflight_test_support import assert_private_dacl
            assert_private_dacl(self, json.loads(result.stdout), current_user_sid())

    def test_worker_exit_kills_descendant(self):
        from trojaino.preflight_windows import K, bind, W, close
        root = str(CLI.parents[3])
        ready = self.root / 'child-pid'
        code = ('import sys,subprocess,time; sys.path.insert(0,sys.argv[1]); '
                'from trojaino.preflight_windows import contain_process; job=contain_process(); '
                'child=subprocess.Popen([sys.executable,"-I","-S","-c","import time; time.sleep(60)"]); '
                'from pathlib import Path; p=Path(sys.argv[2]); '
                'p.with_suffix(".tmp").write_text(str(child.pid)); '
                'p.with_suffix(".tmp").replace(p); time.sleep(60)')
        worker = subprocess.Popen([sys.executable, '-I', '-S', '-c', code, root, str(ready)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        handle = None
        open_process = bind(K, 'OpenProcess', W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
        wait = bind(K, 'WaitForSingleObject', W.DWORD, W.HANDLE, W.DWORD)
        terminate = bind(K, 'TerminateProcess', W.BOOL, W.HANDLE, W.UINT)
        try:
            # Windows communicate() reader threads wait for EOF, so a timeout
            # has no reliable partial stdout while either process holds pipes.
            deadline = time.monotonic() + 10
            while not ready.exists() and worker.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            if not ready.exists():
                if worker.poll() is None:
                    worker.kill()
                output, error = worker.communicate(timeout=5)
                self.fail(f'containment readiness failed: rc={worker.returncode}, stdout={output!r}, stderr={error!r}')
            child_pid = int(ready.read_text())
            handle = open_process(0x100001, False, child_pid)  # synchronize + cleanup termination
            self.assertTrue(handle)
            self.assertIsNone(worker.poll(), 'worker exited before containment probe')
            self.assertEqual(wait(handle, 0), 258, 'child was not alive before worker kill')
            worker.kill()
            self.assertEqual(wait(handle, 5000), 0, 'orphaned child remains alive')
            worker.communicate(timeout=5)
        finally:
            if worker.poll() is None:
                worker.kill()
            if handle:
                if wait(handle, 0) == 258:
                    terminate(handle, 1)
                    self.assertEqual(wait(handle, 5000), 0, 'test child cleanup failed')
                close(handle)
            worker.communicate(timeout=5)

    def test_native_node_siblings_and_ambient_import_denial(self):
        import shutil
        node = shutil.which('node.exe')
        if not node:
            self.skipTest('requires enforcing Node runtime')
        env = dict(os.environ, TROJAINO_NODE=str(Path(node).resolve()), NODE_OPTIONS='--require /absent')
        self.state.mkdir()
        ambient = self.state / 'node_modules/ambient'
        ambient.mkdir(parents=True)
        (ambient / 'index.js').write_text('console.log("AMBIENT_EXECUTED")')
        for code, expected in [('console.log(require("./helper.cjs"))', True), ('require("ambient")', False)]:
            (self.source / 'helper.cjs').write_text('module.exports=42')
            (self.source / 'server.js').write_text(code)
            from preflight_test_support import sealed_gate
            receipt = sealed_gate(self.source, self.state)
            self.assertEqual(receipt['decision'], 'permit', receipt)
            result = subprocess.run([sys.executable, '-I', '-S', str(CLI), 'launch',
                                     receipt['report_path'], '--entry', 'server.js'], env=env,
                                    capture_output=True, text=True, timeout=30)
            if expected:
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, '42\n')
            else:
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn('AMBIENT_EXECUTED', result.stdout)

    def test_native_powershell_canonical_scan(self):
        import shutil
        shell = shutil.which('pwsh.exe') or shutil.which('powershell.exe')
        self.assertIsNotNone(shell)
        command = api.format_command(api.command_prefix('PowerShell') +
                                     ['scan', str(self.source), '--state', str(self.state)], 'PowerShell')
        event = {'hook_event_name': 'PreToolUse', 'tool_name': 'PowerShell', 'tool_input': {'command': command}}
        self.assertNotIn('permissionDecision', api.hook(event)['hookSpecificOutput'])
        result = subprocess.run([shell, '-NoProfile', '-NonInteractive', '-Command', command],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, (command, result.stdout, result.stderr))
        self.assertEqual(json.loads(result.stdout)['decision'], 'permit')
