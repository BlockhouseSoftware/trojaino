"""Prepare a NEW private layout from reviewed source using Python -I -S.

The setup source and interpreter must already be trusted. No global activation,
installs, network, candidate imports or publication. Final bytes are constructed
before writing through pinned directory descriptors or Windows handles.
"""
import argparse
import hashlib
import io
import json
import os
import re
from pathlib import Path
import runpy
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def prepared_hook_manifest(python: str, plugin: Path) -> dict:
    """Build literal hooks; the caller supplies validated executable payload."""
    entry = plugin / 'scripts/preflight.py'
    interpreter = Path(python)
    if (not interpreter.is_absolute() or interpreter.is_symlink()
            or not interpreter.is_file() or not os.access(interpreter, os.X_OK)
            or not entry.is_absolute()):
        raise ValueError('trusted absolute interpreter and entry required')
    handler = {'type': 'command', 'command': python,
               'args': ['-I', '-S', str(entry), 'hook'], 'timeout': 30}
    return {'hooks': {
        'SessionStart': [{'hooks': [dict(handler)]}],
        'PreToolUse': [{'matcher': 'Bash|PowerShell|Write|Edit|MultiEdit|NotebookEdit|Workflow|mcp__.*',
                        'hooks': [dict(handler)]}],
    }}


def coverage_section(text):
    """Extract exactly one reviewed section, independent of checkout newlines."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    start = '## Coverage and security boundaries\n'
    end = '## Verification and rollout status\n'
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError('README coverage section boundaries missing or ambiguous')
    begin = text.index(start) + len(start)
    finish = text.index(end)
    if finish <= begin:
        raise ValueError('README coverage section boundaries out of order or empty')
    return text[begin:finish]


def _render(destination, personal_plugin_name=None):
    if sys.version_info < (3, 11) or not Path(sys.executable).is_absolute():
        raise ValueError('trusted absolute Python 3.11+ required')
    # Explicit reviewed setup source only; the marketplace entry never does this.
    sys.path.insert(0, str(ROOT))
    if os.name == 'nt':
        from trojaino.preflight_paths import windows_path
        windows_path(destination)  # validate raw spelling before Path normalization
    destination = Path(destination)
    if not destination.is_absolute() or destination.exists() or destination.is_symlink():
        raise ValueError('new absolute destination required')
    trusted_python = str(Path(sys.executable).resolve(strict=True))
    if personal_plugin_name is not None and not re.fullmatch(r'trojaino-local-[a-z0-9]+(?:-[a-z0-9]+)*', personal_plugin_name):
        raise ValueError('distinct trojaino-local- identity required')
    if personal_plugin_name is not None and destination.name != personal_plugin_name:
        raise ValueError('final directory basename must match personal plugin identity')
    plugin = destination if personal_plugin_name is not None else destination / 'plugins/trojaino'
    manifest = prepared_hook_manifest(trusted_python, plugin)
    build = runpy.run_path(str(ROOT / 'scripts/build_preflight_bundle.py'))['build']
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / 'source.zip'
        build(archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            payload = {str(Path(name).relative_to('trojaino-source')).replace('\\', '/'):
                       archive.read(name) for name in archive.namelist()}
    entry_key = 'plugins/trojaino/scripts/preflight.py'
    entry_bytes = payload.get(entry_key, b'')
    binding_slot = b'_EXPECTED_BINDING = None\n'
    if entry_bytes.count(binding_slot) != 1:
        raise ValueError('sealed executable binding slot missing or ambiguous')
    binding = (str(plugin / 'scripts/preflight.py'), trusted_python)
    payload[entry_key] = entry_bytes.replace(binding_slot,
        ('_EXPECTED_BINDING = ' + repr(binding) + '\n').encode(), 1)
    payload['plugins/trojaino/hooks/hooks.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    if personal_plugin_name is not None:
        license_bytes = payload['LICENSE']
        prefix = 'plugins/trojaino/'
        payload = {name[len(prefix):]: data for name, data in payload.items() if name.startswith(prefix)}
        payload['LICENSE'] = license_bytes
        skill_key = 'skills/scan/SKILL.md'
        payload[skill_key] = payload[skill_key].replace(b'/trojaino:scan', ('/' + personal_plugin_name + ':scan').encode())
        original_readme = payload['README.md'].decode()
        coverage = coverage_section(original_readme)
        payload['README.md'] = (f'''# {personal_plugin_name} — prepared personal inspection plugin

Experimental, disabled by default. Not a universal execution firewall.
This self-contained runtime is bound to this exact directory and its approved Python.
Do not move it, copy it into a marketplace cache, or alter its bindings.

Identity: `{personal_plugin_name}@skills-dir`.
Use `/{personal_plugin_name}:scan` only after explicit activation has been qualified.
Missing trusted SessionStart context or any hook error means stop; do not assume protection.

The marketplace copy stays inactive. Its uninstall does not remove this local plugin.
Disable this local identity explicitly with `claude plugin disable {personal_plugin_name}@skills-dir`,
verify it with `claude plugin list --json`, and close existing inspection sessions.
Updates require a fresh final directory and distinct identity. Never overwrite this copy.
Removal requires disabling, closing sessions and removing only the approved local directory.

This inspection mode blocks ordinary execution/write tools; it is not an invisible
add-on for unrestricted everyday coding. A clean scan is not a safety guarantee.
Real Claude hook dispatch and native Windows acceptance remain unqualified.

## Coverage and security boundaries

''' + coverage + '\nLicense: AGPL-3.0-only; see [LICENSE](LICENSE).\n').encode()
        plugin_manifest = json.loads(payload['.claude-plugin/plugin.json'])
        plugin_manifest['name'] = personal_plugin_name
        plugin_manifest['defaultEnabled'] = False
        payload['.claude-plugin/plugin.json'] = (json.dumps(plugin_manifest, indent=2) + '\n').encode()
    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()
              if name != 'MANIFEST.sha256.json'}
    payload['MANIFEST.sha256.json'] = (json.dumps(hashes, indent=2, sort_keys=True) + '\n').encode()
    result = {'plugin_dir': str(plugin), 'python': trusted_python,
              'manifest_sha256': hashes['hooks/hooks.json' if personal_plugin_name is not None else 'plugins/trojaino/hooks/hooks.json'],
              'note': 'Keep this layout at this path; reprepare after moving or changing Python.'}
    return payload, result


def prepare(destination, personal_plugin_name=None):
    payload, result = _render(destination, personal_plugin_name)
    write_tree = runpy.run_path(str(ROOT / 'scripts/write_prepared_tree.py'))['write_tree']
    write_tree(destination, payload)
    return result


def plan(destination, personal_plugin_name=None):
    """Render bytes only. Authority requires the verified source/runtime caller."""
    if personal_plugin_name is None:
        raise ValueError('personal plugin identity required for planning')
    payload, _ = _render(destination, personal_plugin_name)
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return output.getvalue()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    parser.add_argument('--personal-plugin-name', help='Create a disabled plugin directly at the new final destination; use a new trojaino-local- identity for each version. Does not enable it or modify settings.')
    parser.add_argument('--plan', action='store_true', help='Render a disabled personal plugin as a ZIP to stdout without creating its final directory. For the reviewed native controller only; not an installer or activation.')
    args = parser.parse_args()
    if args.plan:
        sys.stdout.buffer.write(plan(args.destination, args.personal_plugin_name))
    else:
        print(json.dumps(prepare(args.destination, args.personal_plugin_name)))
