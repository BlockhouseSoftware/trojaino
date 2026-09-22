"""The plugin's sealed Python entry carries the whole scanner and imports nothing from disk."""
import ast
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / 'scripts/build_sealed_runtime.py'


def capsule():
    text = runpy.run_path(str(BUILDER))['render']()
    return next(ast.literal_eval(n.value) for n in ast.parse(text).body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_CAPSULE' for t in n.targets))


def build(directory):
    entry = Path(directory) / 'preflight.py'
    runpy.run_path(str(BUILDER))['build'](entry)
    return entry


def run_image(image, code, *args, cwd=None):
    """Load the image as a worker would, then run test code inside it.

    Without an operation the bootstrap hands over to main() and exits, so the
    image runs a harmless scan of an empty folder first and prints its report.
    Assertions use the last line of output.
    """
    with tempfile.TemporaryDirectory() as empty:
        image = dict(image, operation='scan_path', args=[empty, 'package'])
        return subprocess.run([sys.executable, '-I', '-S', '-c',
                               "import sys,json; _CAPSULE=json.load(sys.stdin); exec(_CAPSULE['bootstrap'])\n" + code,
                               *args], input=json.dumps(image), text=True, capture_output=True,
                              timeout=40, cwd=cwd)


class SealedRuntimeTests(unittest.TestCase):
    def test_identity_binds_the_captured_source_bytes(self):
        code = "import trojaino; print(trojaino._sealed_identity)"
        image = capsule()
        image.update(entry='/unused/preflight.py')
        first = run_image(image, code).stdout.splitlines()[-1]
        image['sources']['trojaino.scanner'] += '\n# different image\n'
        second = run_image(image, code).stdout.splitlines()[-1]
        self.assertTrue(first.strip())
        self.assertNotEqual(first, second)

    def test_worker_scans_from_the_image_and_ignores_a_hostile_tree(self):
        image = capsule()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            candidate = root / 'candidate'
            candidate.mkdir()
            (candidate / 'hello.py').write_text('print(42)\n')
            hostile = root / 'trojaino'
            hostile.mkdir()
            (hostile / '__init__.py').write_text("raise RuntimeError('HOSTILE_RUNTIME_EXECUTED')\n")
            image.update(entry=str(root / 'preflight.py'))
            r = run_image(image, "print(json.dumps(image_worker('scan_path', [sys.argv[1], 'package'])))",
                          str(candidate), cwd=root)
            self.assertEqual(r.returncode, 0, r.stderr)
            report = json.loads(r.stdout.splitlines()[-1])
            self.assertTrue(report['complete'])
            self.assertEqual(report['files_scanned'], 1)
            self.assertNotIn('EXECUTED', r.stdout + r.stderr)

    def test_worker_rejects_a_corrupted_capsule_before_running_it(self):
        bootstrap = capsule()['bootstrap']
        child = next(ast.literal_eval(n.value) for n in ast.parse(bootstrap).body
                     if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_CHILD' for t in n.targets))
        r = subprocess.run([sys.executable, '-I', '-S', '-c', child, '0' * 64],
                           input=b'{"bootstrap":"print(\\"ATTACK_EXECUTED\\")"}\n', capture_output=True, timeout=5)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn(b'ATTACK_EXECUTED', r.stdout + r.stderr)

    def test_shipped_image_is_reproducible(self):
        rendered = runpy.run_path(str(BUILDER))['render']()
        shipped = ROOT / 'plugins/trojaino/scripts/preflight.py'
        # Bytes, not text: read_text() would hide a CRLF checkout. .gitattributes
        # pins LF so this stays a real byte-for-byte comparison.
        self.assertEqual(shipped.read_bytes(), rendered.encode('utf-8'), 'regenerate stale sealed image')

    def test_without_isolation_flags_it_stops_before_importing_anything_nearby(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = build(tmp)
            (Path(tmp) / 'pathlib.py').write_text("print('AMBIENT_EXECUTED')\n")
            result = subprocess.run([sys.executable, str(entry), 'hook'], input='{}',
                                    text=True, capture_output=True, timeout=10)
            # Exit 1 is a non-blocking hook error: Claude shows it and blocks nothing.
            self.assertEqual(result.returncode, 1)
            self.assertIn('Python 3.11', result.stderr)
            self.assertNotIn('AMBIENT_EXECUTED', result.stdout + result.stderr)

    def test_session_start_from_a_copy_outside_the_repository(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = build(tmp)
            result = subprocess.run([sys.executable, '-I', '-S', str(entry), 'hook'],
                                    input=json.dumps({'hook_event_name': 'SessionStart'}),
                                    text=True, capture_output=True, timeout=25, cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            context = json.loads(result.stdout)['hookSpecificOutput']['additionalContext']
            self.assertIn('install gate is active', context)
            self.assertIn(str(entry).replace('\\', '/'), context)

    def test_ordinary_commands_get_no_answer_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = build(tmp)
            event = {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash',
                     'tool_input': {'command': 'npm test && ls'}, 'cwd': tmp}
            result = subprocess.run([sys.executable, '-I', '-S', str(entry), 'hook'],
                                    input=json.dumps(event), text=True, capture_output=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')

    def test_malformed_events_are_ignored_not_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = build(tmp)
            for payload in ('', 'not json', '[]', '{"hook_event_name": "PreToolUse"}'):
                with self.subTest(payload=payload):
                    result = subprocess.run([sys.executable, '-I', '-S', str(entry), 'hook'],
                                            input=payload, text=True, capture_output=True, timeout=25)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertNotIn('"deny"', result.stdout)

    def test_manual_scan_of_a_local_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            entry = build(root)
            candidate = root / 'candidate'
            candidate.mkdir()
            (candidate / 'hello.py').write_text('print(42)\n')
            result = subprocess.run([sys.executable, '-I', '-S', str(entry), 'scan', str(candidate)],
                                    text=True, capture_output=True, timeout=40,
                                    env=dict(os.environ, HOME=str(root), USERPROFILE=str(root),
                                             LOCALAPPDATA=str(root)))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['result'], 'NO CRITICAL RISKS FOUND')


class PackagedRendererTests(unittest.TestCase):
    def test_bootstrap_ships_as_package_source_and_stays_scannable(self):
        bootstrap = ROOT / 'trojaino/claude/sealed_runtime_bootstrap.py'
        # Kept as .py on purpose: Trojaino's own rules keep flagging its exec()
        # in the reviewed release self-scan. A .txt suffix would hide that.
        self.assertIn('exec(', bootstrap.read_text(encoding='utf-8'))

    def test_renderer_resolves_without_a_checkout_layout(self):
        from trojaino.claude import seal
        self.assertTrue(seal.BOOTSTRAP.is_relative_to(seal.PACKAGE))
        self.assertEqual(seal.PACKAGE.name, 'trojaino')

    def test_packaging_helpers_are_excluded_from_the_image(self):
        from trojaino.claude import seal
        sealed = seal.source_map()
        self.assertFalse([name for name in sealed if name.startswith('trojaino.claude')])
        for module in ('trojaino.scanner', 'trojaino.gate', 'trojaino.install_detect', 'trojaino.registry'):
            self.assertIn(module, sealed)

    def test_no_path_binding_survives_in_the_image(self):
        source = (ROOT / 'plugins/trojaino/scripts/preflight.py').read_text(encoding='utf-8')
        self.assertNotIn('_EXPECTED_BINDING', source)


if __name__ == '__main__':
    unittest.main()
