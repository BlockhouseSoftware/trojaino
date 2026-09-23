"""Recognize source overrides without invoking a package manager or package code.

An explicit public version does not override environment or configuration, so
a configuration that changes where an install comes from needs review rather
than a public scan of an unrelated artifact. Only settings that actually select
a source or artifact count: an npm auth token, a proxy, a certificate path or a
config-file pointer on its own changes nothing and is not an override. Values
(which may contain credentials) are never echoed.
"""
from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
import re
import stat
import tomllib

from trojaino.install_detect import _program, _strip_prefix

MAX_CONFIG_BYTES = 1_000_000

# Environment that selects a registry/index directly (value decides) or points
# at a configuration file (the file decides). Matching is case-insensitive.
_REGISTRY_ENV = {"npm_config_registry", "yarn_npm_registry_server", "yarn_registry",
                 "pnpm_registry", "bun_config_registry"}
_INDEX_ENV = {"pip_index_url", "uv_index_url", "uv_default_index"}
_EXTRA_SOURCE_ENV = {"pip_extra_index_url", "pip_find_links", "uv_extra_index_url", "uv_index",
                     "uv_find_links"}
_SELECTION_ENV = {"pip_no_binary", "pip_only_binary", "uv_no_binary", "uv_no_binary_package",
                  "uv_only_binary"}
_SWITCH_ENV = {"pip_no_index", "uv_no_index"}
_FILE_ENV = {"npm_config_userconfig": "npmrc", "npm_config_globalconfig": "npmrc",
             "yarn_rc_filename": "yarnrc", "pip_config_file": "pip", "uv_config_file": "uv"}
SOURCE_ENV = (_REGISTRY_ENV | _INDEX_ENV | _EXTRA_SOURCE_ENV | _SELECTION_ENV | _SWITCH_ENV
              | set(_FILE_ENV))

_DEFAULT_NPM = {"https://registry.npmjs.org", "http://registry.npmjs.org",
                "https://registry.yarnpkg.com", "http://registry.yarnpkg.com"}
_DEFAULT_PYPI = {"https://pypi.org/simple", "https://pypi.python.org/simple"}

_NPM_PROGRAMS = {"npm", "npx", "pnpm", "pnpx", "yarn", "bun", "bunx", "claude"}
_PIP_PROGRAMS = {"pip", "pip3", "python", "python3", "py", "pipx"}
_UV_PROGRAMS = {"uv", "uvx"}

# Options, matched only inside the install command's own arguments.
_NPM_SOURCE_OPTIONS = {"--registry", "--userconfig", "--globalconfig", "--prefix", "-C", "--dir",
                       "--cwd"}
_PY_SOURCE_OPTIONS = {"-i", "--index-url", "--extra-index-url", "-f", "--find-links", "--no-index",
                      "--no-binary", "--only-binary", "--platform", "--python-version",
                      "--implementation", "--abi", "--index", "--default-index", "--config-file",
                      "--with", "--with-editable", "--directory", "--project"}

_CD = re.compile(r"""^\s*(?:cd|pushd|set-location|sl)\s+
                     (?P<dir>'[^'$`\\]*'|"[^"$`\\]*"|[^\s'"$`*?{}\[\];&|<>()]+)
                     \s*(?:&&|;)\s*(?P<rest>.+)$""", re.I | re.X | re.S)
_ANY_CD = re.compile(r"(?:^|[;&|(]\s*)\s*(?:cd|pushd|popd|set-location|sl)(?:\s|$)", re.I)


def working_directory(command: str, cwd: str | None) -> tuple[str, str | None]:
    """The directory the install runs in, or a reason it cannot be known.

    Claude often writes "cd DIR && npm install x". A single leading change to a
    plain, existing directory is resolved; anything else still needs review.
    """
    base = Path(cwd or os.getcwd())
    match = _CD.match(command)
    if match:
        folder = match["dir"].strip("'\"")
        if folder in {"-", ""} or _ANY_CD.search(match["rest"]):
            return str(base), "the command changes directory more than once; run the install in its target directory"
        target = Path(os.path.expanduser(folder))
        target = target if target.is_absolute() else base / target
        if not target.is_dir():
            return str(base), "the command changes to a directory Trojaino cannot find"
        return str(target.resolve()), None
    if _ANY_CD.search(command):
        return str(base), "the command changes directory before installation; run the install in its target directory"
    return str(base), None


def _default(value: str, defaults: set[str]) -> bool:
    return value.strip().strip("'\"").rstrip("/").lower() in defaults


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _selects(value: str) -> bool:
    return value.strip().lower() not in {"", ":none:", "false", "0", "no", "off"}


def _scope_hit(scope: str, names: set[str]) -> bool:
    scope = scope.strip().strip("'\"").lstrip("@").lower()
    return any(name.startswith(f"@{scope}/") for name in names)


def _mentions(keys, names: set[str]) -> bool:
    """Whether override/resolution keys such as "**/a/@s/b@1" name a target."""
    for key in keys:
        for name in names:
            if re.search(r"(?:^|/)" + re.escape(name) + r"(?:@|$)", str(key).lower()):
                return True
    return False


def _nested_keys(value) -> list:
    if not isinstance(value, dict):
        return []
    return [k for key, item in value.items() for k in (key, *_nested_keys(item))]


def _read(path: Path) -> str | None:
    """File text; None when absent. Raises ValueError when not safely readable."""
    try:
        info = path.stat()  # follows links: a dotfile manager's symlink is fine
    except FileNotFoundError:
        return None
    except NotADirectoryError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_CONFIG_BYTES:
        raise ValueError("configuration is not a regular, readable file")
    return path.read_text(encoding="utf-8-sig")


def _npmrc(text: str, names: set[str]) -> bool:
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")) or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        if key == "registry" and not _default(value, _DEFAULT_NPM):
            return True
        scoped = re.fullmatch(r"(@[^:]+):registry", key)
        if scoped and _scope_hit(scoped[1], names):
            return True
    return False


def _yarnrc(text: str, names: set[str]) -> bool:
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or parts[0].startswith("#"):
            continue
        key = parts[0].strip("'\"").lower()
        if key == "registry" and not _default(parts[1], _DEFAULT_NPM):
            return True
        scoped = re.fullmatch(r"(@[^:]+):registry", key)
        if scoped and _scope_hit(scoped[1], names):
            return True
    return False


def _yarnrc_yml(text: str, names: set[str]) -> bool:
    in_scopes = False
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        top = not line[:1].isspace()
        if top:
            in_scopes = False
            key, _, value = line.partition(":")
            key = key.strip().strip("'\"")
            if key == "npmRegistryServer" and not _default(value, _DEFAULT_NPM):
                return True
            in_scopes = key == "npmScopes"
        elif in_scopes:
            m = re.fullmatch(r"( {1,4}|\t)['\"]?([A-Za-z0-9_.-]+)['\"]?\s*:\s*", line.rstrip())
            if m and _scope_hit(m[2], names):
                return True
    return False


def _pnpm_workspace(text: str, names: set[str]) -> bool:
    keys = {line.partition(":")[0].strip() for line in text.splitlines()
            if line and not line[:1].isspace() and not line.startswith("#")}
    if keys & {"registry", "registries"}:
        return True
    return bool(keys & {"overrides", "patchedDependencies", "packageExtensions"}) and any(
        re.search(r"^\s+['\"]?(?:[^'\"\s]*/)?" + re.escape(name) + r"(?:@|['\"]?\s*:)", text, re.M)
        for name in names)


def _package_json(text: str, names: set[str]) -> bool:
    data = json.loads(text)
    if not isinstance(data, dict):
        return False
    pnpm = data.get("pnpm") if isinstance(data.get("pnpm"), dict) else {}
    keys = (_nested_keys(data.get("overrides")) + _nested_keys(data.get("resolutions"))
            + _nested_keys(data.get("patchedDependencies")) + _nested_keys(pnpm.get("overrides"))
            + _nested_keys(pnpm.get("patchedDependencies")))
    return _mentions(keys, names)


def _bunfig(text: str, names: set[str]) -> bool:
    install = tomllib.loads(text).get("install")
    if not isinstance(install, dict):
        return False
    registry = install.get("registry")
    if registry is not None:
        url = registry.get("url", "") if isinstance(registry, dict) else str(registry)
        if not _default(url, _DEFAULT_NPM):
            return True
    scopes = install.get("scopes")
    return isinstance(scopes, dict) and any(_scope_hit(s, names) for s in scopes)


def _pip_conf(text: str) -> bool:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read_string(text)
    for section in parser.sections():
        for key, value in parser.items(section):
            key = key.replace("_", "-")
            if key == "index-url" and not _default(value, _DEFAULT_PYPI):
                return True
            if key in {"extra-index-url", "find-links"} and value.strip():
                return True
            if key == "no-index" and _truthy(value):
                return True
            if key in {"no-binary", "only-binary"} and _selects(value):
                return True
    return False


def _normalized(keys) -> list[str]:
    return [re.sub(r"[-_.]+", "-", str(key)).lower() for key in keys]


def _uv_settings(table, names: set[str]) -> bool:
    if not isinstance(table, dict):
        return False
    for key in ("index", "extra-index-url", "find-links"):
        if table.get(key):
            return True
    if table.get("index-url") and not _default(str(table["index-url"]), _DEFAULT_PYPI):
        return True
    if table.get("no-index") is True or table.get("no-binary") is True:
        return True
    if _mentions(_normalized(table.get("no-binary-package") or []), names):
        return True
    for key in ("sources", "override-dependencies", "constraint-dependencies"):
        value = table.get(key)
        entries = value if isinstance(value, dict) else {}
        if isinstance(value, list):
            entries = {re.split(r"[\s<>=!~;\[@]", str(item), maxsplit=1)[0]: 1 for item in value}
        if _mentions(_normalized(entries), names):
            return True
    return _uv_settings(table.get("pip"), names) if "pip" in table else False


def _uv_toml(text: str, names: set[str]) -> bool:
    return _uv_settings(tomllib.loads(text), names)


def _pyproject(text: str, names: set[str]) -> bool:
    return _uv_settings(tomllib.loads(text).get("tool", {}).get("uv"), names)


def _env(key: str) -> str | None:
    return next((value for name, value in os.environ.items() if name.lower() == key), None)


def _environment_override(families: set[str], names: set[str]) -> tuple[str | None, list]:
    """(overriding variable names, extra config files to inspect)."""
    found, files = [], []
    for name, value in os.environ.items():
        key = name.lower()
        if key not in SOURCE_ENV:
            continue
        family = "npm" if key.startswith(("npm_", "yarn_", "pnpm_", "bun_")) else (
            "uv" if key.startswith("uv_") else "pip")
        if family not in families:
            continue
        if key in _FILE_ENV:
            if value.strip() and value.strip() != os.devnull:
                files.append((Path(os.path.expanduser(value.strip())), _FILE_ENV[key]))
            continue
        if key in _REGISTRY_ENV and _default(value, _DEFAULT_NPM):
            continue
        if key in _INDEX_ENV and _default(value, _DEFAULT_PYPI):
            continue
        if key in _SWITCH_ENV and not _truthy(value):
            continue
        if key in _SELECTION_ENV and not _selects(value):
            continue
        if key in _EXTRA_SOURCE_ENV and not value.strip():
            continue
        found.append(name)
    return (", ".join(sorted(found)) or None), files


def _config_files(root: Path, families: set[str], programs: set[str]) -> list[tuple[Path, str]]:
    home = Path.home()
    files: list[tuple[Path, str]] = []
    folders = list(dict.fromkeys([root, *root.parents, home]))
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    appdata = os.environ.get("APPDATA")
    if "npm" in families:
        for folder in folders:
            files += [(folder / ".npmrc", "npmrc"), (folder / "package.json", "package")]
            if programs & {"yarn"} or not programs:
                files += [(folder / ".yarnrc", "yarnrc"), (folder / ".yarnrc.yml", "yarnrc_yml")]
            if programs & {"pnpm", "pnpx"} or not programs:
                files += [(folder / ".pnpmfile.cjs", "pnpmfile"),
                          (folder / "pnpm-workspace.yaml", "pnpm_workspace")]
            if programs & {"bun", "bunx"} or not programs:
                files.append((folder / "bunfig.toml", "bunfig"))
        files += [(Path(p), "npmrc") for p in ("/etc/npmrc", "/usr/local/etc/npmrc",
                                               "/opt/homebrew/etc/npmrc")]
        prefix = _env("npm_config_prefix")
        if prefix:
            files.append((Path(prefix) / "etc" / "npmrc", "npmrc"))
    if "pip" in families:
        files += [(Path(p), "pip") for p in ("/etc/pip.conf", "/etc/xdg/pip/pip.conf")]
        files += [(config_home / "pip" / "pip.conf", "pip"), (home / ".pip" / "pip.conf", "pip"),
                  (home / "Library" / "Application Support" / "pip" / "pip.conf", "pip")]
        if appdata:
            files.append((Path(appdata) / "pip" / "pip.ini", "pip"))
        if os.environ.get("VIRTUAL_ENV"):
            venv = Path(os.environ["VIRTUAL_ENV"])
            files += [(venv / "pip.conf", "pip"), (venv / "pip.ini", "pip")]
    if "uv" in families:
        files += [(folder / "uv.toml", "uv") for folder in folders]
        files += [(folder / "pyproject.toml", "pyproject") for folder in folders]
        files += [(config_home / "uv" / "uv.toml", "uv"), (Path("/etc/uv/uv.toml"), "uv")]
        if appdata:
            files.append((Path(appdata) / "uv" / "uv.toml", "uv"))
    return files


_PARSERS = {"npmrc": _npmrc, "yarnrc": _yarnrc, "yarnrc_yml": _yarnrc_yml,
            "pnpm_workspace": _pnpm_workspace, "package": _package_json, "bunfig": _bunfig,
            "uv": _uv_toml, "pyproject": _pyproject,
            "pnpmfile": lambda text, names: True,  # readPackage hooks can rewrite anything
            "pip": lambda text, names: _pip_conf(text)}


def _families(attempts: list) -> tuple[set[str], set[str]]:
    families: set[str] = set()
    programs: set[str] = set()
    for attempt in attempts:
        tokens = _strip_prefix(getattr(attempt, "tokens", []) or [])
        program = _program(tokens[0].text) if tokens else ""
        if re.fullmatch(r"(?:pip|python)3\.\d+", program):
            program = "pip"
        programs.add(program)
        for target in attempt.targets:
            if target.ecosystem in {"npm", "plugin"}:
                families.add("npm")
            elif target.ecosystem == "pypi":
                if program in _UV_PROGRAMS:
                    families.add("uv")
                elif program in _PIP_PROGRAMS:
                    families.add("pip")
                else:
                    families.update({"pip", "uv"})
    programs.discard("")
    unknown = programs - _NPM_PROGRAMS - _PIP_PROGRAMS - _UV_PROGRAMS
    return families, set() if unknown else programs


def _source_option(attempts: list) -> bool:
    for attempt in attempts:
        ecosystems = {t.ecosystem for t in attempt.targets}
        options = set()
        if ecosystems & {"npm", "plugin"}:
            options |= _NPM_SOURCE_OPTIONS
        if "pypi" in ecosystems:
            options |= _PY_SOURCE_OPTIONS
        for token in getattr(attempt, "tokens", []) or []:
            if token.text.partition("=")[0] in options:
                return True
    return False


def source_warning(command: str, attempts: list, cwd: str | None) -> str | None:
    names = {t.name.lower() for a in attempts for t in a.targets if t.ecosystem in {"npm", "pypi"}}
    families, programs = _families(attempts)
    if not families:
        return None
    if re.search(r"\b(?:npm|pnpm|yarn|pip|pip3|uv)\s+config\s+(?:set|edit|delete|unset)\b", command, re.I):
        return "the command changes package-manager configuration before installation"
    if _source_option(attempts):
        return "the command changes package source, artifact selection or installation context"
    variables, pointed = _environment_override(families, names)
    if variables:
        return "a package source or artifact-selection environment override is active (" + variables + ")"
    assigned = {k.lower() for k in re.findall(r"(?:^|[\s;&|:])([A-Za-z_][A-Za-z0-9_]*)\s*=", command)}
    if assigned & SOURCE_ENV:
        return "the command sets a package source or artifact-selection environment override"
    root = Path(cwd or os.getcwd()).absolute()
    try:
        for path, kind in [*_config_files(root, families, programs), *pointed]:
            text = _read(path)
            if text is not None and _PARSERS[kind](text, names):
                return "package-manager configuration changes source or artifact selection"
    except (OSError, UnicodeError, ValueError, TypeError, AttributeError,
            configparser.Error, tomllib.TOMLDecodeError):
        return "package-manager configuration could not be read"
    return None
