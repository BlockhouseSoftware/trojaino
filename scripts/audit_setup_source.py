"""Developer-only source ZIP audit against immutable Git objects; no source execution.

This does not approve the source code or qualify the installer. Supply a reviewed
literal commit, archive hash, layout version and absolute developer Git executable.
No checkout, filters, source imports, hooks, downloads or user configuration edits.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import runpy
import subprocess

_HELPER = runpy.run_path(str(Path(__file__).with_name('build_windows_setup_payload.py')))
_COMMON = ('LICENSE', 'README.md', 'pyproject.toml', 'scripts/build_preflight_bundle.py',
           'scripts/prepare_preflight_plugin.py', 'scripts/write_prepared_tree.py',
           'scripts/build_sealed_runtime.py', 'scripts/sealed_runtime_bootstrap.py',
           'docs/windows-preflight.md', 'docs/marketplace-lifecycle.md',
           'docs/marketplace-requirements.md', 'docs/marketplace-runtime-architecture.md',
           'docs/personal-plugin-delivery.md')
# Historical layouts stay frozen so archives built from earlier commits still audit.
LAYOUTS = {
    'source-layout-v1': frozenset(_COMMON + ('.claude-plugin/marketplace.json', 'docs/sig-windows-trial.md')),
    'source-layout-v2': frozenset(_COMMON + ('.claude-plugin/marketplace.json', 'docs/sig-windows-trial.md',
                                             'docs/friendly-setup-architecture.md')),
    'source-layout-v3': frozenset(_COMMON + ('docs/windows-trial-checklist.md',
                                             'docs/friendly-setup-architecture.md')),
}
FIXED = LAYOUTS['source-layout-v3']


def audit(data, source_sha256, repo, source_commit, git, layout):
    if not re.fullmatch(r'[0-9a-f]{40}', source_commit):
        raise ValueError('literal lowercase full source commit required')
    if not re.fullmatch(r'[0-9a-f]{64}', source_sha256):
        raise ValueError('literal lowercase SHA256 required')
    if layout not in LAYOUTS:
        raise ValueError('explicit supported source layout required')
    if not Path(git).is_absolute() or not Path(git).is_file():
        raise ValueError('absolute developer Git executable required')
    files = _HELPER['verified_archive'](data, source_sha256)
    def command(*args):
        return subprocess.check_output([str(git), '--no-replace-objects', '-C', str(repo), *args],
                                       stderr=subprocess.PIPE, timeout=30)
    if command('rev-parse', '--verify', source_commit + '^{commit}').decode().strip() != source_commit:
        raise ValueError('Git commit object mismatch')
    entries = {}
    for record in command('ls-tree', '-r', '-z', source_commit).split(b'\0'):
        if not record:
            continue
        metadata, path = record.split(b'\t', 1)
        mode, kind, oid = metadata.decode('ascii').split()
        name = path.decode('utf-8')
        entries[name] = (mode, kind, oid)
    selected = set(LAYOUTS[layout])
    for name in entries:
        path = PurePosixPath(name)
        if (name.startswith('trojaino/') and path.suffix == '.py'
                or name.startswith('plugins/trojaino/') and '__pycache__' not in path.parts
                and path.suffix in {'.py', '.sh', '.json', '.md'}):
            selected.add(name)
    expected = {'trojaino-source/' + name for name in selected} | {'trojaino-source/MANIFEST.sha256.json'}
    if set(files) != expected or not selected.issubset(entries):
        raise ValueError('Git source inventory mismatch')
    hashes = {}
    for name in sorted(selected):
        mode, kind, oid = entries[name]
        if mode not in ('100644', '100755') or kind != 'blob':
            raise ValueError('Git source must contain regular file blobs only')
        packaged = files['trojaino-source/' + name]
        size = int(command('cat-file', '-s', oid))
        if size != len(packaged) or size > _HELPER['MAX_FILE_BYTES']:
            raise ValueError('Git source byte length mismatch: ' + name)
        if command('cat-file', 'blob', oid) != packaged:
            raise ValueError('Git source bytes differ: ' + name)
        hashes[name] = hashlib.sha256(packaged).hexdigest()
    manifest = (json.dumps(hashes, sort_keys=True, indent=2) + '\n').encode()
    if files['trojaino-source/MANIFEST.sha256.json'] != manifest:
        raise ValueError('Git-derived source manifest mismatch')
    return {'verified_source_commit': source_commit, 'source_sha256': source_sha256,
            'layout': layout, 'source_files': len(hashes),
            'classification': 'git-object-byte-provenance-only'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    parser.add_argument('--git', type=Path, required=True)
    parser.add_argument('--layout', choices=tuple(LAYOUTS), required=True)
    args = parser.parse_args()
    print(json.dumps(audit(_HELPER['read_archive'](args.source), args.source_sha256, args.repo,
                           args.source_commit, args.git, args.layout), sort_keys=True))
