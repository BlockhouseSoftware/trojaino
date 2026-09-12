"""Source provenance is checked against Git objects, not a ZIP manifest claim."""
import hashlib
import io
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/audit_setup_source.py'
FIXED = ('LICENSE', 'README.md', 'pyproject.toml', 'scripts/build_preflight_bundle.py',
         'scripts/prepare_preflight_plugin.py', 'scripts/write_prepared_tree.py',
         'scripts/build_sealed_runtime.py', 'scripts/sealed_runtime_bootstrap.py',
         '.claude-plugin/marketplace.json', 'docs/windows-preflight.md',
         'docs/sig-windows-trial.md', 'docs/marketplace-lifecycle.md',
         'docs/marketplace-requirements.md', 'docs/marketplace-runtime-architecture.md',
         'docs/personal-plugin-delivery.md')


def packed(files):
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, data in dict(files, **{'MANIFEST.sha256.json': (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()}).items():
            archive.writestr('trojaino-source/' + name, data)
    return output.getvalue()


class SourceAuditTests(unittest.TestCase):
    def test_commit_inventory_and_every_byte_are_verified_without_running_source(self):
        self.assertTrue(SCRIPT.is_file(), 'missing independent Git source provenance auditor')
        audit = runpy.run_path(str(SCRIPT))['audit']
        git_command = shutil.which('git')
        if git_command is None:
            self.fail('Git developer tool required for source provenance test')
        git = str(Path(git_command).resolve())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def command(*args):
                return subprocess.check_output([git, '-C', str(root), *args], stderr=subprocess.STDOUT)
            command('init', '-q')
            files = {name: b'not executed\n' for name in FIXED}
            files['trojaino/__init__.py'] = b'raise RuntimeError("must never execute source")\n'
            files['plugins/trojaino/scripts/preflight.py'] = b'also never executed\n'
            for name, data in files.items():
                target = root / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
            command('add', '.')
            command('-c', 'user.name=Source Audit Test', '-c', 'user.email=audit@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')
            commit = command('rev-parse', 'HEAD').decode().strip()
            data = packed(files)
            result = audit(data, hashlib.sha256(data).hexdigest(), root, commit, git, 'source-layout-v1')
            self.assertEqual(result['verified_source_commit'], commit)
            self.assertEqual(result['source_files'], len(files))
            self.assertEqual(result['classification'], 'git-object-byte-provenance-only')
            # The worktree is not source authority; neither it nor packaged source is executed.
            (root / 'trojaino/__init__.py').write_text('modified working tree')
            self.assertEqual(result, audit(data, hashlib.sha256(data).hexdigest(), root, commit, git, 'source-layout-v1'))
            for changed in (dict(files, **{'trojaino/__init__.py': b'altered'}),
                            {k: v for k, v in files.items() if k != 'trojaino/__init__.py'},
                            dict(files, **{'unreviewed.py': b'extra'})):
                bad = packed(changed)  # Self-consistent manifest cannot grant provenance.
                with self.subTest(inventory=sorted(changed)):
                    with self.assertRaisesRegex(ValueError, 'Git'):
                        audit(bad, hashlib.sha256(bad).hexdigest(), root, commit, git, 'source-layout-v1')
            for bad_data, bad_pin, tool, layout in (
                (b'not a ZIP', hashlib.sha256(data).hexdigest(), git, 'source-layout-v1'),
                (data, 'not-a-digest', git, 'source-layout-v1'),
                (data, hashlib.sha256(data).hexdigest(), 'git', 'source-layout-v1'),
                (data, hashlib.sha256(data).hexdigest(), git, 'unknown-layout'),
            ):
                with self.assertRaises(ValueError):
                    audit(bad_data, bad_pin, root, commit, tool, layout)
            # Canonical derived manifest is required even when all source bytes match.
            manifest_bad = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(data)) as original, zipfile.ZipFile(manifest_bad, 'w') as changed:
                for info in original.infolist():
                    changed.writestr(info, b'{}' if info.filename.endswith('/MANIFEST.sha256.json') else original.read(info))
            bad = manifest_bad.getvalue()
            with self.assertRaisesRegex(ValueError, 'manifest'):
                audit(bad, hashlib.sha256(bad).hexdigest(), root, commit, git, 'source-layout-v1')
            # v2 explicitly adds the new architecture document, never infers it from a manifest.
            files['docs/friendly-setup-architecture.md'] = b'new architecture\n'
            (root / 'docs/friendly-setup-architecture.md').write_bytes(files['docs/friendly-setup-architecture.md'])
            command('add', 'docs/friendly-setup-architecture.md')
            command('-c', 'user.name=Source Audit Test', '-c', 'user.email=audit@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'layout v2')
            second = command('rev-parse', 'HEAD').decode().strip()
            data_v2 = packed(files)
            result_v2 = audit(data_v2, hashlib.sha256(data_v2).hexdigest(), root, second, git, 'source-layout-v2')
            self.assertEqual(result_v2['source_files'], len(files))
            with self.assertRaisesRegex(ValueError, 'Git'):
                audit(data_v2, hashlib.sha256(data_v2).hexdigest(), root, second, git, 'source-layout-v1')
            # A Git symlink blob must be refused even with identical packaged bytes.
            oid = command('rev-parse', second + ':trojaino/__init__.py').decode().strip()
            command('update-index', '--cacheinfo', '120000,' + oid + ',trojaino/__init__.py')
            command('-c', 'user.name=Source Audit Test', '-c', 'user.email=audit@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '-qm', 'symlink fixture')
            symlink_commit = command('rev-parse', 'HEAD').decode().strip()
            with self.assertRaisesRegex(ValueError, 'regular'):
                audit(data_v2, hashlib.sha256(data_v2).hexdigest(), root, symlink_commit, git, 'source-layout-v2')
            for malformed in (commit.upper(), commit[:7], '--help', commit + '\n'):
                with self.assertRaisesRegex(ValueError, 'literal'):
                    audit(data, hashlib.sha256(data).hexdigest(), root, malformed, git, 'source-layout-v1')


if __name__ == '__main__':
    unittest.main()
