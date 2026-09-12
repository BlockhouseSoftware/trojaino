"""Offline setup packaging: never execute archive members or edit user config."""
import hashlib
import io
from pathlib import Path
import runpy
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/build_windows_setup_payload.py'


def archive_bytes(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)
    return output.getvalue()


class SetupPayloadTests(unittest.TestCase):
    def helper(self):
        self.assertTrue(SCRIPT.is_file(), 'missing offline pinned setup payload builder')
        return runpy.run_path(str(SCRIPT))

    def test_archive_is_pinned_before_parsing_and_returns_exact_bytes(self):
        helper = self.helper()
        data = archive_bytes([('python.exe', b'not executed'), ('LICENSE.txt', b'license')])
        digest = hashlib.sha256(data).hexdigest()
        self.assertEqual(helper['verified_archive'](data, digest),
                         {'python.exe': b'not executed', 'LICENSE.txt': b'license'})
        with self.assertRaisesRegex(ValueError, 'digest'):
            helper['verified_archive'](b'not even a zip', digest)
        with self.assertRaisesRegex(ValueError, 'digest'):
            helper['verified_archive'](data, '0' * 64)

    def test_archive_rejects_windows_aliases_links_and_collisions(self):
        helper = self.helper()
        cases = [
            [('.. /escape', b'x')], [('../escape', b'x')], [('/absolute', b'x')],
            [('C:/drive', b'x')], [('a\\b', b'x')], [('a//b', b'x')],
            [('a/./b', b'x')], [('a:stream', b'x')], [('NUL.txt', b'x')],
            [('COM1', b'x')], [('trailing.', b'x')], [('trailing ', b'x')],
            [('name\x01', b'x')], [('a', b'x'), ('A', b'y')],
            [('dir/a', b'x'), ('DIR/b', b'y')],
            [('a', b'x'), ('a/b', b'y')], [('a/b', b'y'), ('a', b'x')],
        ]
        for entries in cases:
            with self.subTest(entries=entries):
                data = archive_bytes(entries)
                with self.assertRaises(ValueError):
                    helper['verified_archive'](data, hashlib.sha256(data).hexdigest())
        for mode in (0o120777, 0o020600, 0o040755):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                info = zipfile.ZipInfo('special')
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, b'target')
            data = stream.getvalue()
            with self.assertRaisesRegex(ValueError, 'regular'):
                helper['verified_archive'](data, hashlib.sha256(data).hexdigest())

    def test_archive_budgets_bound_compressed_and_expanded_bytes(self):
        helper = self.helper()
        self.assertIn('MAX_ARCHIVE_BYTES', helper, 'missing compressed input budget')
        verify = helper['verified_archive']
        data = archive_bytes([('a', b'x' * 32), ('b', b'y' * 32)])
        digest = hashlib.sha256(data).hexdigest()
        for override in ({'MAX_ARCHIVE_BYTES': len(data) - 1},
                         {'MAX_FILES': 1}, {'MAX_FILE_BYTES': 31},
                         {'MAX_TOTAL_BYTES': 63}):
            with self.subTest(override=override):
                from unittest.mock import patch
                with patch.dict(verify.__globals__, override):
                    with self.assertRaisesRegex(ValueError, 'budget'):
                        verify(data, digest)
        self.assertEqual(len(verify(data, digest)), 2)

    def test_build_preserves_all_bytes_and_binds_both_inputs(self):
        import json
        import tempfile
        from unittest.mock import patch
        helper = self.helper()
        self.assertIn('build', helper, 'missing deterministic setup payload build')
        build = helper['build']
        source_builder = runpy.run_path(str(ROOT / 'scripts/build_preflight_bundle.py'))['build']
        runtime = archive_bytes([('python.exe', b'never executed'), ('python314._pth', b'python314.zip\n.\n'),
                                 ('LICENSE.txt', b'Python license'), ('python314.zip', b'vendor stdlib')])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_path = root / 'runtime.zip'
            runtime_path.write_bytes(runtime)
            source_path = root / 'source.zip'
            source_result = source_builder(source_path)
            source_sha = source_result['sha256']
            commit = 'c038a6c34399f615a622c8c685f8497d0b5dc237'
            with patch.dict(build.__globals__, {'RUNTIME_SHA256': hashlib.sha256(runtime).hexdigest()}):
                first = root / 'setup-1.zip'
                result = build(runtime_path, source_path, source_sha, commit, first)
                second = root / 'setup-2.zip'
                build(runtime_path, source_path, source_sha, commit, second)
                self.assertEqual(first.read_bytes(), second.read_bytes())
                self.assertEqual(result['sha256'], hashlib.sha256(first.read_bytes()).hexdigest())
                with zipfile.ZipFile(first) as outer:
                    self.assertEqual(outer.read('runtime.zip'), runtime)
                    self.assertEqual(outer.read('source.zip'), source_path.read_bytes())
                    metadata = json.loads(outer.read('payload.json'))
                    self.assertEqual(metadata['declared_source_commit'], commit)
                    self.assertEqual(metadata['archives']['source.zip']['sha256'], source_sha)
                    source_files = helper['verified_archive'](source_path.read_bytes(), source_sha)
                    self.assertEqual(metadata['archives']['source.zip']['files'],
                        {name: hashlib.sha256(data).hexdigest() for name, data in source_files.items()})
                    self.assertIn('LICENSE.txt', metadata['archives']['runtime.zip']['files'])
                    self.assertEqual(metadata['classification'], 'engineering-only-not-an-installer')
                before = first.read_bytes()
                with self.assertRaises(FileExistsError):
                    build(runtime_path, source_path, source_sha, commit, first)
                self.assertEqual(first.read_bytes(), before)
                for source_digest, declared in [('0' * 64, commit), (source_sha, 'bad-commit')]:
                    denied = root / 'denied.zip'
                    with self.assertRaises(ValueError):
                        build(runtime_path, source_path, source_digest, declared, denied)
                    self.assertFalse(denied.exists())

    def test_failed_publication_leaves_no_partial_artifact_or_temp_file(self):
        import tempfile
        from unittest.mock import patch
        helper = self.helper()
        self.assertIn('publish_new', helper, 'missing failure-safe artifact publication')
        publish = helper['publish_new']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / 'artifact.zip'
            with patch.object(publish.__globals__['os'], 'fsync', side_effect=OSError('disk failure')):
                with self.assertRaisesRegex(OSError, 'disk failure'):
                    publish(target, b'complete archive bytes')
            self.assertEqual(list(root.iterdir()), [])
            publish(target, b'complete archive bytes')
            with self.assertRaises(FileExistsError):
                publish(target, b'replacement')
            self.assertEqual(target.read_bytes(), b'complete archive bytes')
            self.assertEqual(list(root.iterdir()), [target])

    def test_malformed_or_unsupported_zip_is_a_controlled_rejection(self):
        helper = self.helper()
        ordinary = archive_bytes([('file', b'data')])
        cases = [b'not a ZIP', ordinary[:-30]]
        for compression in (zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA):
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', compression=compression) as archive:
                archive.writestr('file', b'data')
            cases.append(stream.getvalue())
        for data in cases:
            with self.subTest(size=len(data)):
                with self.assertRaisesRegex(ValueError, 'archive'):
                    helper['verified_archive'](data, hashlib.sha256(data).hexdigest())

    def test_dos_special_attributes_are_not_regular_files(self):
        verify = self.helper()['verified_archive']
        for attributes in (0x10, 0x08, (0o100644 << 16) | 0x10):
            with self.subTest(attributes=attributes):
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, 'w') as archive:
                    info = zipfile.ZipInfo('special')
                    info.create_system = 0
                    info.external_attr = attributes
                    archive.writestr(info, b'not a regular file')
                data = stream.getvalue()
                with self.assertRaisesRegex(ValueError, 'regular'):
                    verify(data, hashlib.sha256(data).hexdigest())


if __name__ == '__main__':
    unittest.main()
