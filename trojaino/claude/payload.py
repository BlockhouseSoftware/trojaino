"""Assemble the Claude Code plugin directory from packaged source.

The files under ``payload/`` are the canonical copies. ``plugins/trojaino`` in
the repository is generated from them, the way the sealed entry already is, so
one edit cannot leave the two out of step.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

from trojaino.claude import seal

PAYLOAD = Path(__file__).resolve().parent / 'payload'


def _hook(timeout: int) -> dict:
    # Exec form: no shell on any platform, so nothing in the event can be
    # interpreted as shell syntax. Claude Code fills in CLAUDE_PLUGIN_ROOT.
    return {'type': 'command', 'command': 'python3',
            'args': ['-I', '-S', '${CLAUDE_PLUGIN_ROOT}/scripts/preflight.py', 'hook'],
            'timeout': timeout}


# Live from the moment the plugin is installed. The PreToolUse matcher covers
# the tools that can install software or change which MCP servers load.
HOOKS = {'hooks': {
    'SessionStart': [{'hooks': [_hook(30)]}],
    'PreToolUse': [{'matcher': 'Bash|PowerShell|Write|Edit|MultiEdit', 'hooks': [_hook(150)]}],
}}


def source_files() -> dict[str, bytes]:
    """The canonical payload bytes, keyed by their path inside the plugin."""
    return {
        '.claude-plugin/plugin.json': (PAYLOAD / 'plugin.json').read_bytes(),
        'README.md': (PAYLOAD / 'README.md').read_bytes(),
        'skills/scan/SKILL.md': (PAYLOAD / 'SKILL.md').read_bytes(),
        'skills/doctor/SKILL.md': (PAYLOAD / 'DOCTOR.md').read_bytes(),
        'LICENSE': (PAYLOAD / 'LICENSE').read_bytes(),
    }


def marketplace_files() -> dict[str, bytes]:
    """The distributable plugin directory, exactly as Claude Code installs it."""
    files = source_files()
    del files['LICENSE']  # the repository's own LICENSE covers the checked-in copy
    files['hooks/hooks.json'] = (json.dumps(HOOKS, indent=2) + '\n').encode()
    files['scripts/preflight.py'] = seal.render().encode('utf-8')
    files['integrity.json'] = (json.dumps({'version': seal.version(), 'files': {
        name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())
    }}, indent=2) + '\n').encode()
    return files
