"""Recognize source overrides without invoking a package manager or package code.

An explicit public version does not override environment or configuration.
Unknown source-selection contexts require review rather than a public scan of
an unrelated artifact. Values (which may contain credentials) are never echoed.
"""
from __future__ import annotations

import os
import json
import tomllib
from pathlib import Path
import re

SOURCE_ENV = re.compile(r"^(?:npm_config_(?:registry|userconfig|globalconfig)|"
                        r"yarn_(?:npm_registry_server|rc_filename)|pnpm_(?:registry|config_file)|bun_config_.*|"
                        r"pip_(?:index_url|extra_index_url|find_links|config_file|no_binary|only_binary)|"
                        r"uv_(?:index.*|default_index|find_links|config_file|no_binary.*))$", re.I)
SOURCE_OPTIONS = re.compile(
    r"(?:^|\s)(?:--(?:registry|userconfig|globalconfig|dir|cwd|directory|config|config-file|"
    r"index-url|extra-index-url|index|default-index|find-links|no-index|no-binary|only-binary|"
    r"python-version|platform|implementation|abi|with|with-editable)|-[iCf])(?:=|\s|$)")
CONFIG_SOURCE = re.compile(r"registry|index[-_]?url|extra[-_]?index|default[-_]?index|"
                           r"find[-_]?links|no[-_]?binary|only[-_]?binary|"
                           r"\[tool\.uv|\[install|npmRegistryServer|npmScopes|"
                           r'"(?:overrides|resolutions|patchedDependencies)"', re.I)


def source_warning(command: str, attempts: list, cwd: str | None) -> str | None:
    ecosystems = {t.ecosystem for a in attempts for t in a.targets}
    if not ecosystems & {"npm", "pypi", "plugin"}:
        return None
    if re.search(r"\b(?:npm|pnpm|yarn|pip|pip3)\s+config\s+(?:set|edit|delete)\b", command, re.I):
        return "the command changes package-manager configuration before installation"
    if SOURCE_OPTIONS.search(command):
        return "the command changes package source, artifact selection or installation context"
    overrides = sorted(key for key in os.environ if SOURCE_ENV.fullmatch(key))
    if overrides:
        return "a package source or artifact-selection environment override is active (" + ", ".join(overrides) + ")"
    if any(SOURCE_ENV.fullmatch(key) for key in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*=", command)):
        return "the command sets a package source or artifact-selection environment override"
    if re.search(r"(?:^|[;&|]\s*)\s*(?:cd|pushd|set-location)\s", command, re.I):
        return "the command changes directory before installation; run the install in its target directory"
    root = Path(cwd or os.getcwd()).absolute()
    paths: set[Path] = set()
    for folder in [root, *root.parents, Path.home()]:
        if "npm" in ecosystems:
            paths.update(folder / name for name in (".npmrc", ".yarnrc", ".yarnrc.yml", ".pnpmfile.cjs",
                                                    "pnpm-workspace.yaml", "bunfig.toml", "package.json"))
        if "pypi" in ecosystems:
            paths.update(folder / name for name in ("pip.ini", "pip.conf", "uv.toml", "pyproject.toml"))
    # System and conventional per-user configuration locations.
    if "npm" in ecosystems:
        paths.update(Path(p) for p in ("/etc/npmrc", "/usr/local/etc/npmrc", "/opt/homebrew/etc/npmrc"))
        # A global install prefix is common on Windows and does not itself
        # choose a registry. Inspect its npmrc instead of rejecting the prefix.
        prefix = next((value for key, value in os.environ.items() if key.lower() == 'npm_config_prefix'), None)
        if prefix:
            paths.add(Path(prefix)/'etc/npmrc')
    if "pypi" in ecosystems:
        paths.update([Path('/etc/pip.conf'), Path.home()/'.config/pip/pip.conf',
                      Path.home()/'.pip/pip.conf', Path.home()/'.config/uv/uv.toml'])
        if os.environ.get('APPDATA'):
            paths.update(Path(os.environ['APPDATA']) / p for p in ('pip/pip.ini', 'uv/uv.toml'))
    try:
        for path in paths:
            if not path.exists():
                continue
            if path.is_symlink() or path.stat().st_size > 1_000_000:
                return "package-manager configuration cannot be inspected reliably"
            text = path.read_text(encoding='utf-8')
            if path.name == 'package.json':
                data = json.loads(text)
                source_change = any(key in data for key in ('overrides', 'resolutions', 'patchedDependencies'))
                source_change = source_change or bool(data.get('pnpm', {}).get('patchedDependencies'))
            elif path.name == 'pyproject.toml':
                data = tomllib.loads(text)
                source_change = bool(data.get('tool', {}).get('uv', {}))
            else:
                source_change = path.name in {'.pnpmfile.cjs', 'uv.toml', 'bunfig.toml'} or CONFIG_SOURCE.search(text)
            if source_change:
                return "package-manager configuration changes source or artifact selection"
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError):
        return "package-manager configuration could not be read"
    return None
