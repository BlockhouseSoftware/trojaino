"""Assemble the Claude Code plugin directory from packaged source.

The files under ``payload/`` are the canonical copies. ``plugins/trojaino`` in
the repository is generated from them, the way the sealed entry already is, so
one edit cannot leave the two out of step.
"""
from __future__ import annotations

import json
from pathlib import Path

from trojaino.claude import seal

PAYLOAD = Path(__file__).resolve().parent / 'payload'
# An unprepared copy registers no hooks. Preparation replaces this with literal
# interpreter and entry paths; until then the plugin provides no protection.
INERT_HOOKS = {'hooks': {}}


def source_files() -> dict[str, bytes]:
    """The canonical payload bytes, keyed by their path inside the plugin."""
    return {
        '.claude-plugin/plugin.json': (PAYLOAD / 'plugin.json').read_bytes(),
        'README.md': (PAYLOAD / 'README.md').read_bytes(),
        'skills/scan/SKILL.md': (PAYLOAD / 'SKILL.md').read_bytes(),
        'LICENSE': (PAYLOAD / 'LICENSE').read_bytes(),
    }


def marketplace_files() -> dict[str, bytes]:
    """The inert, distributable plugin directory: no hooks, no binding."""
    files = source_files()
    del files['LICENSE']  # the repository's own LICENSE covers the checked-in copy
    files['hooks/hooks.json'] = (json.dumps(INERT_HOOKS, indent=2) + '\n').encode()
    files['scripts/preflight.py'] = seal.render().encode('utf-8')
    return files
