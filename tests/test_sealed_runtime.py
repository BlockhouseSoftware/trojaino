"""Behavioral checks for the sealed marketplace runtime boundary."""
import ast
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

def capsule():
    text = runpy.run_path(str(ROOT / 'scripts/build_sealed_runtime.py'))['render']()
    return next(ast.literal_eval(n.value) for n in ast.parse(text).body
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_CAPSULE' for t in n.targets))


class SealedRuntimeTests(unittest.TestCase):
    def test_identity_binds_the_captured_source_bytes(self):
        image = capsule()
        image.update(entry='/unused/preflight.py', operation='scanner_identity', args=[])
        def identity():
            r = subprocess.run([sys.executable, '-I', '-S', '-c',
                "import sys,json; _CAPSULE=json.load(sys.stdin); exec(_CAPSULE['bootstrap'])"],
                input=json.dumps(image), text=True, capture_output=True, timeout=25)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)
        first = identity()
        image['sources']['trojaino.scanner'] += '\n# different reviewed image\n'
        self.assertNotEqual(first, identity())
        second = identity()
        image['bootstrap'] += '\n# changed bootstrap\n'
        self.assertNotEqual(second, identity())

    def test_isolated_operations_use_the_same_image(self):
        image = capsule()
        image.update(entry='/unused/preflight.py', operation='scanner_identity', args=[])
        code = ("import sys,json; _CAPSULE=json.load(sys.stdin); exec(_CAPSULE['bootstrap']); "
                "from trojaino.preflight import isolated_operation; "
                "print(json.dumps(isolated_operation('scanner_identity', [])))")
        r = subprocess.run([sys.executable, '-I', '-S', '-c', code],
                           input=json.dumps(image), text=True, capture_output=True, timeout=25)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], lines[1])

    def test_hook_worker_preserves_input_and_has_a_deadline(self):
        image = capsule()
        image.update(entry='/unused/preflight.py', operation='scanner_identity', args=[])
        code = ("import sys,json,tempfile; _CAPSULE=json.load(sys.stdin); exec(_CAPSULE['bootstrap']); "
                "from trojaino.preflight import isolated_operation; "
                "f=tempfile.TemporaryFile(); f.write(b'{\"hook_event_name\":\"SessionStart\"}'); f.seek(0); "
                "print(json.dumps(isolated_operation('hook_input', [], stdin=f)))")
        r = subprocess.run([sys.executable, '-I', '-S', '-c', code],
                           input=json.dumps(image), text=True, capture_output=True, timeout=25)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout.splitlines()[-1])['hookSpecificOutput']['hookEventName'], 'SessionStart')

    def test_worker_ignores_replaced_entry_and_hostile_runtime_tree(self):
        image = capsule()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            candidate = root / 'candidate'
            candidate.mkdir()
            (candidate / 'hello.py').write_text('print(42)\n')
            entry = root / 'preflight.py'
            entry.write_text("raise RuntimeError('REPLACEMENT_EXECUTED')\n")
            hostile = root / 'trojaino'
            hostile.mkdir()
            (hostile / '__init__.py').write_text("raise RuntimeError('HOSTILE_RUNTIME_EXECUTED')\n")
            image.update(entry=str(entry), operation='scanner_identity', args=[])
            code = ("import sys,json; _CAPSULE=json.load(sys.stdin); exec(_CAPSULE['bootstrap']); "
                    "print(json.dumps(image_worker('scan_path', [sys.argv[1]])))")
            r = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(candidate)],
                cwd=root, input=json.dumps(image), text=True, capture_output=True, timeout=25)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(json.loads(r.stdout.splitlines()[-1])['complete'])
            self.assertNotIn('EXECUTED', r.stdout + r.stderr)

    def test_worker_rejects_corrupted_capsule_before_execution(self):
        bootstrap = capsule()['bootstrap']
        child = next(ast.literal_eval(n.value) for n in ast.parse(bootstrap).body
                     if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_CHILD' for t in n.targets))
        r = subprocess.run([sys.executable, '-I', '-S', '-c', child, '0' * 64],
            input=b'{"bootstrap":"print(\\"ATTACK_EXECUTED\\")"}\n', capture_output=True, timeout=5)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn(b'ATTACK_EXECUTED', r.stdout + r.stderr)

    def test_shipped_image_is_reproducible_without_a_loose_runtime(self):
        rendered = runpy.run_path(str(ROOT / 'scripts/build_sealed_runtime.py'))['render']()
        shipped = ROOT / 'plugins/trojaino/scripts/preflight.py'
        self.assertTrue(shipped.read_text() == rendered, 'regenerate stale sealed image')
        self.assertFalse((ROOT / 'plugins/trojaino/runtime').exists(), 'remove obsolete loose runtime')

    def test_worker_preserves_explicit_node_but_not_ambient_options(self):
        image = capsule()
        image['sources']['trojaino.preflight'] += "\ndef scanner_identity():\n    return [os.environ.get('TROJAINO_NODE'), os.environ.get('NODE_OPTIONS')]\n"
        image.update(entry='/unused/preflight.py', operation='scanner_identity', args=[])
        code = ("import sys,json,os; _CAPSULE=json.load(sys.stdin); exec(_CAPSULE['bootstrap']); "
                "os.environ['TROJAINO_NODE']='/approved/node'; os.environ['NODE_OPTIONS']='--hostile'; "
                "print(json.dumps(image_worker('scanner_identity', [])))")
        r = subprocess.run([sys.executable, '-I', '-S', '-c', code],
                           input=json.dumps(image), text=True, capture_output=True, timeout=25)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout.splitlines()[-1]), ['/approved/node', None])

    def test_nonisolated_entry_denies_before_importing_adjacent_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / 'preflight.py'
            runpy.run_path(str(ROOT / 'scripts/build_sealed_runtime.py'))['build'](entry)
            (Path(tmp) / 'pathlib.py').write_text("print('AMBIENT_EXECUTED')\nraise RuntimeError('ambient')\n")
            result = subprocess.run([sys.executable, str(entry), 'capabilities'],
                                    text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('AMBIENT_EXECUTED', result.stdout + result.stderr)

    def test_blocked_hook_input_times_out_without_hanging_parent(self):
        image = capsule()
        image.update(entry='/unused/preflight.py', operation='scanner_identity', args=[])
        code = ("import sys,json,os; _CAPSULE=json.load(sys.stdin); exec(_CAPSULE['bootstrap']); "
                "from trojaino.preflight import isolated_operation,Denied; "
                "r,w=os.pipe(); source=os.fdopen(r,'rb',buffering=0)\n"
                "try: isolated_operation('hook_input', [], timeout=0.3, stdin=source)\n"
                "except Denied: print('EXPECTED_TIMEOUT_DENY')\n"
                "else: raise AssertionError('blocked input did not deny')\n")
        result = subprocess.run([sys.executable, '-I', '-S', '-c', code],
                                input=json.dumps(image), text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('EXPECTED_TIMEOUT_DENY', result.stdout)

    def test_generated_entry_runs_without_runtime_tree(self):
        builder = ROOT / 'scripts/build_sealed_runtime.py'
        self.assertTrue(builder.is_file(), 'sealed runtime builder required')
        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / 'preflight.py'
            runpy.run_path(str(builder))['build'](entry)
            result = subprocess.run([sys.executable, '-I', '-S', str(entry), 'capabilities'],
                                    text=True, capture_output=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['runtime_storage'], 'sealed-memory')

    def test_scan_uses_sealed_worker_without_source_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            entry = root / 'preflight.py'
            runpy.run_path(str(ROOT / 'scripts/build_sealed_runtime.py'))['build'](entry)
            candidate = root / 'candidate'
            candidate.mkdir()
            (candidate / 'hello.py').write_text('print(42)\n')
            result = subprocess.run([sys.executable, '-I', '-S', str(entry), 'scan',
                                     str(candidate), '--state', str(root / 'state')],
                                    text=True, capture_output=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['decision'], 'permit')

    def test_generated_hook_prefix_is_the_sealed_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / 'preflight.py'
            runpy.run_path(str(ROOT / 'scripts/build_sealed_runtime.py'))['build'](entry)
            result = subprocess.run([sys.executable, '-I', '-S', str(entry), 'hook'],
                input=json.dumps({'hook_event_name': 'SessionStart'}),
                text=True, capture_output=True, timeout=25)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(entry), result.stdout)
            self.assertNotIn('<sealed>', result.stdout)

if __name__ == '__main__':
    unittest.main()
