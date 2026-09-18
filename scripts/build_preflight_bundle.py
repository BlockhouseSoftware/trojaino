"""Build an allowlisted source-only ZIP; requires an external trusted Python.

No installs, credentials, global configuration, Git operations or publishing.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(output):
    files = [ROOT / name for name in ('LICENSE', 'README.md', 'pyproject.toml',
                                      'scripts/build_preflight_bundle.py',
                                      'scripts/prepare_preflight_plugin.py',
                                      'scripts/write_prepared_tree.py',
                                      'scripts/build_sealed_runtime.py',
                                      'scripts/sealed_runtime_bootstrap.py')]
    files += sorted((ROOT / 'trojaino').rglob('*.py'))
    files += sorted(p for p in (ROOT / 'plugins/trojaino').rglob('*')
                    if p.is_file() and '__pycache__' not in p.parts
                    and p.suffix in {'.py', '.sh', '.json', '.md'})
    files += [ROOT / name for name in (
        'docs/windows-preflight.md', 'docs/windows-trial-checklist.md',
        'docs/marketplace-lifecycle.md', 'docs/marketplace-requirements.md',
        'docs/marketplace-runtime-architecture.md', 'docs/personal-plugin-delivery.md',
        'docs/friendly-setup-architecture.md')]
    payload = {}
    for path in files:
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != ROOT.parent):
            raise ValueError('source symlink is not distributable')
        payload[path.relative_to(ROOT).as_posix()] = path.read_bytes()
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())}
    payload['MANIFEST.sha256.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    # Exclusive creation protects a previous reviewed artifact from replacement.
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo('trojaino-source/' + name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return {'artifact': str(output), 'sha256': hashlib.sha256(Path(output).read_bytes()).hexdigest(),
            'source_files': len(manifest), 'kind': 'source-only; no bundled interpreter'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.output)))
