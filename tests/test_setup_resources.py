"""Developer-only compiled trust adapter; no runtime execution or user config."""
import hashlib
import io
import runpy
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/build_setup_resources.py'


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return stream.getvalue()


def sha(data):
    return hashlib.sha256(data).hexdigest()


class SetupResourcesTests(unittest.TestCase):
    def test_compiled_pins_bind_payload_and_independently_approved_inputs(self):
        self.assertTrue(SCRIPT.is_file(), 'missing compiled approved payload resource generator')
        render = runpy.run_path(str(SCRIPT))['render']
        runtime = archive({'python.exe': b'not executed', 'LICENSE.txt': b'preserved'})
        source = archive({'scripts/prepare.py': b'not executed'})
        payload = archive({'runtime.zip': runtime, 'source.zip': source, 'payload.json': b'not trusted for hashes'})
        commit = 'c038a6c34399f615a622c8c685f8497d0b5dc237'
        with patch.dict(render.__globals__, {'RUNTIME_SHA256': sha(runtime)}):
            generated = render(payload, sha(payload), sha(source), commit)
            self.assertEqual(generated, render(payload, sha(payload), sha(source), commit))
            for value in (sha(payload), sha(runtime), sha(source), sha(b'not executed'), commit):
                self.assertIn(value, generated)
            self.assertIn('StageRuntime(string destination)', generated)
            self.assertIn('StageSource(string destination)', generated)
            self.assertIn('RuntimeMembers()', generated)
            self.assertIn('SourceMembers()', generated)
            self.assertIn('return new[] {"LICENSE.txt", "python.exe"};', generated)
            self.assertIn('return new[] {"scripts/prepare.py"};', generated)
            self.assertIn('GetManifestResourceStream', generated)
            self.assertNotIn('not trusted for hashes', generated)
            for data, pin, source_pin, revision in [
                (b'not a ZIP', sha(payload), sha(source), commit),
                (payload, '0' * 64, sha(source), commit),
                (payload, sha(payload), '0' * 64, commit),
                (payload, sha(payload), sha(source), 'bad-commit'),
            ]:
                with self.subTest(pin=pin, source=source_pin, revision=revision):
                    with self.assertRaises(ValueError):
                        render(data, pin, source_pin, revision)
            changed = archive({'runtime.zip': archive({'python.exe': b'changed'}), 'source.zip': source, 'payload.json': b'{}'})
            with self.assertRaisesRegex(ValueError, 'digest'):
                render(changed, sha(changed), sha(source), commit)

    def test_generator_rejects_inputs_the_native_stager_cannot_accept(self):
        render = runpy.run_path(str(SCRIPT))['render']
        source = archive({'a.txt': b'source'})
        cases = []
        for name in ('a' * 121, '/'.join(['a'] * 13), 'a' * 110 + '/' + 'b' * 100):
            cases.append(archive({name: b'not executed'}))
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            info = zipfile.ZipInfo('a.txt')
            info.external_attr = (0o100644 << 16) | 0x400
            z.writestr(info, b'not executed')
        cases.append(stream.getvalue())
        for runtime in cases:
            payload = archive({'runtime.zip': runtime, 'source.zip': source, 'payload.json': b'{}'})
            with self.subTest(runtime_sha=sha(runtime)):
                with patch.dict(render.__globals__, {'RUNTIME_SHA256': sha(runtime)}):
                    with self.assertRaisesRegex(ValueError, 'native'):
                        render(payload, sha(payload), sha(source), 'c038a6c34399f615a622c8c685f8497d0b5dc237')


if __name__ == '__main__':
    unittest.main()
