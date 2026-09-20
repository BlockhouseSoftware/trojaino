"""Prepare a personal Trojaino plugin from the installed package.

Runs on any platform with a trusted Python 3.11+. The interpreter running this
code is the trust anchor: its absolute path is written into the prepared hooks,
so installing Trojaino with pipx (or any isolated environment you chose) is what
decides which interpreter Claude Code will execute.

Nothing here enables anything, edits Claude settings, or touches the network.
"""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import sys

IDENTITY_PREFIX = 'trojaino-local-'


def skills_directory() -> Path:
    """The Claude Code skills directory this interpreter would install into."""
    configured = os.environ.get('CLAUDE_CONFIG_DIR')
    base = Path(configured) if configured else Path.home() / '.claude'
    return base / 'skills'


def new_identity(version: str) -> str:
    """A fresh, version-qualified identity. Never reuses an existing directory."""
    digits = ''.join(character for character in version if character.isalnum())
    return f'{IDENTITY_PREFIX}{digits}-{secrets.token_hex(4)}'


def existing_installations(skills: Path) -> list[Path]:
    if not skills.is_dir():
        return []
    return sorted(path for path in skills.iterdir()
                  if path.is_dir() and path.name.startswith(IDENTITY_PREFIX))


def plan_setup(version: str, *, skills: Path | None = None) -> dict:
    """Decide what would be written. Performs no filesystem changes."""
    root = skills if skills is not None else skills_directory()
    identity = new_identity(version)
    return {
        'identity': identity,
        'destination': str(root / identity),
        'python': str(Path(sys.executable).resolve(strict=True)),
        'skills_directory': str(root),
        'existing': [path.name for path in existing_installations(root)],
    }


def run_setup(version: str, *, skills: Path | None = None, dry_run: bool = False) -> dict:
    proposal = plan_setup(version, skills=skills)
    if dry_run:
        proposal['written'] = False
        return proposal
    root = Path(proposal['skills_directory'])
    root.mkdir(parents=True, exist_ok=True)

    from trojaino.claude.prepare import prepare

    result = prepare(proposal['destination'], proposal['identity'])
    proposal['written'] = True
    proposal['manifest_sha256'] = result['manifest_sha256']
    return proposal
