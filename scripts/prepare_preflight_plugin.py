"""Prepare a NEW private trusted source layout with literal exec-form hooks.

Run using the reviewed absolute Python 3.11+ executable with -I -S. Never run
from candidate source. Destination's existing parent must be trusted/user-owned.
No shell, global settings, installs, or candidate code are involved.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def prepare(destination):
    if sys.version_info < (3, 11) or not Path(sys.executable).is_absolute():
        raise ValueError('trusted absolute Python 3.11+ required')
    # Only our reviewed source is added, never cwd, site packages or PYTHONPATH.
    sys.path.insert(0, str(ROOT))
    if os.name == 'nt':
        from trojaino.preflight_paths import windows_path
        # Preserve raw spelling until validation; Path would collapse aliases.
        windows_path(destination)
    destination = Path(destination)
    if not destination.is_absolute() or destination.exists() or destination.is_symlink():
        raise ValueError('new absolute destination required')
    if os.name == 'nt':
        from trojaino.preflight_windows import locked_path, private_directory
        with locked_path(str(destination.parent)):
            private_directory(destination)
    else:
        if any(p.is_symlink() for p in [destination.parent, *destination.parents]):
            raise ValueError('symlink parent unsupported')
        destination.mkdir(mode=0o700)
    build = runpy.run_path(str(ROOT / 'scripts/build_preflight_bundle.py'))['build']
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / 'source.zip'
        build(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            # This archive was generated above from the trusted allowlist only.
            for name in archive.namelist():
                relative = Path(name).relative_to('trojaino-source')
                target = destination / relative
                if os.name == 'nt':
                    windows_path(str(target))
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                with target.open('xb') as output:
                    output.write(archive.read(name))
    plugin = destination / 'plugins/trojaino'
    manifest_path = plugin / 'hooks/hooks.json'
    manifest = json.loads(manifest_path.read_text())
    for groups in manifest['hooks'].values():
        for group in groups:
            for handler in group['hooks']:
                handler['command'] = sys.executable
                handler['args'] = ['-I', '-S', str(plugin / 'scripts/preflight.py'), 'hook']
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    # Source hashes in the copied bundle must describe the configured manifest.
    hashes_path = destination / 'MANIFEST.sha256.json'
    hashes = json.loads(hashes_path.read_text())
    hashes['plugins/trojaino/hooks/hooks.json'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    hashes_path.write_text(json.dumps(hashes, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return {'plugin_dir': str(plugin), 'python': sys.executable,
            'manifest_sha256': hashes['plugins/trojaino/hooks/hooks.json'],
            'note': 'Keep this complete layout at this path; reprepare after moving or changing Python.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    args = parser.parse_args()
    print(json.dumps(prepare(args.destination)))
