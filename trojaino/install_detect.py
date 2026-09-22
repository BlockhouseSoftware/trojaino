"""Recognise attempts to install or add software in a shell command.

The install gate only acts on what this module recognises. Anything it does
not recognise passes through untouched: Trojaino is an install gate, not a
general command filter, so ordinary commands must never be slowed or blocked.

Three outcomes per install attempt:

- a *target* Trojaino can fetch and scan (npm, PyPI, GitHub, a local folder);
- an *unscannable* install it can name but not vet (system installers,
  private registries, remote MCP servers, `curl | sh`), which falls back to
  Claude's permission prompt with a warning;
- nothing: not an install, or an install of dependencies the project already
  declares (`npm install`, `pip install -r requirements.txt`, `pip install -e .`).

Each target records the character span of the token that named it, so the
gate can rewrite that one token to pin the exact version it scanned.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import json
import re

# ---------------------------------------------------------------- data types


@dataclass(frozen=True)
class Token:
    text: str   # the word after quote removal
    start: int  # span in the original command, quotes included
    end: int
    quoted: str  # "'", '"' or '' for the opening quote style
    plain: bool  # no variables, globs, command substitution or escapes


@dataclass(frozen=True)
class Target:
    ecosystem: str        # "npm" | "pypi" | "github" | "local"
    name: str             # package name, "owner/repo", or an absolute path
    spec: str | None      # version, tag, ref or specifier as written
    token: Token | None   # the token to rewrite when pinning; None = no rewrite
    extras: str = ""      # PyPI extras such as "[cli]", kept when pinning
    alias: str = ""       # npm alias prefix such as "my-name@npm:"
    subdir: str = ""      # plugin path inside a GitHub repository
    pin_style: str = "=="  # how this tool spells an exact version: "==" or "@"


@dataclass
class Attempt:
    command: str                    # the segment text, for messages
    targets: list[Target] = field(default_factory=list)
    unscannable: str | None = None  # plain-English reason, or None


# ------------------------------------------------------------------ tokenise

_OPERATORS = ("&&", "||", ";", "|", "&", "\n", "(", ")")


def tokenize(command: str, tool: str) -> list[list[Token]]:
    """Split into segments of tokens. Raises ValueError when unsure."""
    escape = "`" if tool == "PowerShell" else "\\"
    segments: list[list[Token]] = [[]]
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if c in " \t\r":
            i += 1
            continue
        op = next((o for o in _OPERATORS if command.startswith(o, i)), None)
        if op is not None:
            # A leading "&" is PowerShell's call operator, not a separator.
            if op == "&" and tool == "PowerShell" and not segments[-1]:
                i += 1
                continue
            segments.append([])
            i += len(op)
            continue
        if c == "#":
            # A comment runs to the end of the line in both shells.
            end = command.find("\n", i)
            i = n if end < 0 else end
            continue
        start = i
        text: list[str] = []
        quoted = ""
        plain = True
        while i < n and command[i] not in " \t\r\n;|&()":
            ch = command[i]
            if ch in "'\"":
                if not text and not quoted:
                    quoted = ch
                close = command.find(ch, i + 1)
                if close < 0:
                    raise ValueError("unbalanced quote")
                inner = command[i + 1:close]
                if ch == '"' and ("$" in inner or "`" in inner or escape in inner):
                    plain = False
                text.append(inner)
                i = close + 1
                continue
            if ch == escape:
                plain = False
                if i + 1 < n:
                    text.append(command[i + 1])
                i += 2
                continue
            if ch in "$`*?{}[]~<>" and not (ch in "[]" and tool == "Bash"):
                plain = False
            text.append(ch)
            i += 1
        segments[-1].append(Token("".join(text), start, i, quoted, plain))
    return [s for s in segments if s]


# ------------------------------------------------------------- helpers

_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")
_WRAPPERS = {"sudo", "doas", "env", "time", "nohup", "command", "exec", "nice", "stdbuf"}


def _program(word: str) -> str:
    base = re.split(r"[\\/]", word)[-1].lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base


def _strip_prefix(tokens: list[Token]) -> list[Token]:
    i = 0
    while i < len(tokens):
        word = tokens[i].text
        if _ASSIGNMENT.fullmatch(word) and not tokens[i].quoted:
            i += 1
        elif _program(word) in _WRAPPERS:
            i += 1
            while i < len(tokens) and tokens[i].text.startswith("-"):
                i += 1
        else:
            break
    return tokens[i:]


def _positionals(tokens: list[Token], takes_value: set[str]) -> tuple[list[Token], dict[str, str]]:
    """Positional arguments and the flags seen, honouring flags that take values."""
    positional: list[Token] = []
    flags: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        word = tokens[i].text
        if word == "--":
            positional.extend(tokens[i + 1:])
            break
        if word.startswith("-") and len(word) > 1:
            name, eq, value = word.partition("=")
            if not eq and name in takes_value and i + 1 < len(tokens):
                value = tokens[i + 1].text
                i += 1
            flags[name] = value
        else:
            positional.append(tokens[i])
        i += 1
    return positional, flags


# ------------------------------------------------------------------ npm

_NPM_NAME = re.compile(r"(?:@[a-z0-9][a-z0-9._~-]*/)?[a-z0-9][a-z0-9._~-]*", re.I)
_GITHUB_SHORT = re.compile(r"(?:github:)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:#(.+))?")
_GITHUB_URL = re.compile(
    r"(?:git\+)?(?:https://|ssh://git@|git@)github\.com[/:]([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?(?:#(.+))?")


def _local_path(word: str) -> bool:
    return (word.startswith(("./", "../", "/", "~/", ".\\", "..\\", "file:"))
            or re.match(r"[A-Za-z]:[\\/]", word) is not None or word in {".", ".."})


def npm_target(token: Token) -> Target | str | None:
    """A Target, an unscannable reason, or None for a local/project path."""
    word = token.text
    if not token.plain:
        return "the package name is built from variables or globs"
    alias = ""
    m = re.fullmatch(r"([^@/]+|@[^/]+/[^@]+)@npm:(.+)", word)
    if m:
        alias, word = m.group(1) + "@npm:", m.group(2)
    if _local_path(word):
        return None
    gh = _GITHUB_URL.fullmatch(word)
    if gh:
        return Target("github", f"{gh[1]}/{gh[2]}", gh[3], None)
    if word.startswith(("http://", "https://", "git+", "git:", "git@", "ssh:")):
        return "it installs from a URL Trojaino cannot fetch"
    if word.startswith(("gitlab:", "bitbucket:", "gist:")):
        return "it installs from a git host Trojaino does not support"
    if word.startswith("github:") or ("/" in word and not word.startswith("@")):
        gh = _GITHUB_SHORT.fullmatch(word)
        if gh:
            return Target("github", f"{gh[1]}/{gh[2]}", gh[3], None)
        return "the package source is not recognised"
    name, spec = word, None
    at = word.find("@", 1)
    if at > 0:
        name, spec = word[:at], word[at + 1:] or None
    if not _NPM_NAME.fullmatch(name):
        return "the package name is not recognised"
    return Target("npm", name.lower(), spec, token, alias=alias)


_NPM_VALUE_FLAGS = {"--registry", "--tag", "-w", "--workspace", "--prefix", "--omit",
                    "--include", "--install-strategy", "--cache", "--userconfig",
                    "--globalconfig", "-C", "--dir", "--filter", "--save-prefix",
                    "--loglevel", "-p", "--package", "-c", "--call", "--shell"}
_NPM_INSTALL = {"install", "i", "in", "ins", "inst", "insta", "instal", "isnt", "isntal",
                "isntall", "add"}


def _npm_packages(tokens: list[Token], attempt: Attempt) -> None:
    positional, flags = _positionals(tokens, _NPM_VALUE_FLAGS)
    if "--registry" in flags:
        attempt.unscannable = "it uses a custom package registry"
        return
    for token in positional:
        result = npm_target(token)
        if isinstance(result, Target):
            attempt.targets.append(result)
        elif isinstance(result, str):
            attempt.unscannable = result
            return
        elif token.text not in {".", "./", ".\\"}:
            # "." is the project itself: its declared dependencies, not new software.
            path = token.text[5:] if token.text.startswith("file:") else token.text
            attempt.targets.append(Target("local", path, None, None))


def _npx(args: list[Token], attempt: Attempt) -> None:
    """npx / bunx / pnpm dlx / yarn dlx / npm exec: the package is what runs."""
    positional, flags = _positionals_until_package(args)
    if flags.get("_unreadable_source"):
        attempt.unscannable = "the package-source option could not be read reliably"
        return
    if "--registry" in flags:
        attempt.unscannable = "it uses a custom package registry"
        return
    packages = flags.get("packages", [])
    tokens = packages or positional[:1]
    for token in tokens:
        result = npm_target(token)
        if isinstance(result, Target):
            attempt.targets.append(result)
        elif isinstance(result, str):
            attempt.unscannable = result
            return
        else:
            attempt.targets.append(Target("local", token.text.removeprefix("file:"), None, None))


def _positionals_until_package(args: list[Token]) -> tuple[list[Token], dict]:
    """npx flags stop at the first positional: everything after it belongs to the tool."""
    flags: dict = {}
    i = 0
    while i < len(args):
        word = args[i].text
        if word == "--":
            return args[i + 1:i + 2], flags
        if word.startswith("-") and len(word) > 1:
            name, eq, value = word.partition("=")
            if not eq and name in _NPM_VALUE_FLAGS and i + 1 < len(args):
                flags[name] = args[i + 1]
                if name in {"-p", "--package"}:
                    flags.setdefault("packages", []).append(args[i + 1])
                i += 2
                continue
            # "--package=x" names a package too; its span starts after the "=".
            flags[name] = (Token(value, args[i].start + len(name) + 1, args[i].end, "", args[i].plain)
                           if eq and not args[i].quoted else True)
            if name in {"-p", "--package"}:
                if isinstance(flags[name], Token):
                    flags.setdefault("packages", []).append(flags[name])
                else:
                    flags["_unreadable_source"] = True
            i += 1
            continue
        return [args[i]], flags
    return [], flags


# ------------------------------------------------------------------ PyPI

_PEP503 = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?")
_REQUIREMENT = re.compile(
    r"(?P<name>[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?)(?P<extras>\[[A-Za-z0-9._,\- ]*\])?"
    r"(?P<spec>\s*(?:===?|~=|!=|<=|>=|<|>)\s*[^;\s]+)?")


def pypi_target(token: Token) -> Target | str | None:
    word = token.text
    if not token.plain:
        return "the package name is built from variables or globs"
    if _local_path(word) or word.endswith((".whl", ".tar.gz", ".zip")) and not word.startswith("http"):
        return None
    gh = _GITHUB_URL.fullmatch(word.split("@", 1)[-1].strip())
    if gh:
        return Target("github", f"{gh[1]}/{gh[2]}", gh[3], None)
    if "://" in word or word.startswith("git+"):
        return "it installs from a URL Trojaino cannot fetch"
    m = _REQUIREMENT.fullmatch(word.split(";", 1)[0].strip())
    if not m:
        return "the package name is not recognised"
    spec = (m["spec"] or "").replace(" ", "") or None
    return Target("pypi", re.sub(r"[-_.]+", "-", m["name"]).lower(), spec, token,
                  extras=m["extras"] or "")


_PIP_VALUE_FLAGS = {"-r", "--requirement", "-c", "--constraint", "-e", "--editable", "-i",
                    "--index-url", "--extra-index-url", "-f", "--find-links", "-t", "--target",
                    "--prefix", "--root", "--python-version", "--platform", "--implementation",
                    "--abi", "--progress-bar", "--log", "--cache-dir", "--src",
                    "--upgrade-strategy", "--global-option", "-C", "--config-settings",
                    "--trusted-host", "--python", "-p", "--with", "--from", "--spec",
                    "--group", "--extra", "--index", "--default-index", "--only-binary",
                    "--no-binary", "--report", "--proxy", "--timeout", "--retries"}
_PRIVATE_INDEX = {"-i", "--index-url", "--extra-index-url", "-f", "--find-links",
                  "--index", "--default-index"}


def _pip_packages(tokens: list[Token], attempt: Attempt) -> None:
    positional, flags = _positionals(tokens, _PIP_VALUE_FLAGS)
    if _PRIVATE_INDEX & set(flags):
        attempt.unscannable = "it uses a custom package index"
        return
    for token in positional:
        result = pypi_target(token)
        if isinstance(result, Target):
            attempt.targets.append(result)
        elif isinstance(result, str):
            attempt.unscannable = result
            return
        elif token.text not in {".", ".."}:
            attempt.targets.append(Target("local", token.text, None, None))


def _uvx(args: list[Token], attempt: Attempt, at_style: bool = False) -> None:
    """uvx / uv tool / pipx. uv spells a pinned positional as pkg@1.2; pipx needs pkg==1.2."""
    positional, flags = _positionals_until_package_pip(args)
    if _PRIVATE_INDEX & set(flags):
        attempt.unscannable = "it uses a custom package index"
        return
    source = flags.get("--from") or flags.get("--spec")
    if source and not isinstance(source, Token):
        attempt.unscannable = "the package-source option could not be read reliably"
        return
    tokens = [source] if isinstance(source, Token) else positional[:1]
    style = "@" if at_style and not isinstance(source, Token) else "=="
    for token in tokens:
        # uvx accepts pkg@version; read it as pkg==version.
        m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?@([A-Za-z0-9._+!-]+)", token.text)
        if m and token.plain:
            version = None if m[3] == "latest" else "==" + m[3]
            attempt.targets.append(Target("pypi", re.sub(r"[-_.]+", "-", m[1]).lower(), version,
                                          token, extras=m[2] or "", pin_style=style))
            continue
        result = pypi_target(token)
        if isinstance(result, Target):
            if result.ecosystem == "pypi":
                result = Target(result.ecosystem, result.name, result.spec, result.token,
                                result.extras, pin_style=style)
            attempt.targets.append(result)
        elif isinstance(result, str):
            attempt.unscannable = result
            return


def _positionals_until_package_pip(args: list[Token]) -> tuple[list[Token], dict]:
    flags: dict = {}
    i = 0
    while i < len(args):
        word = args[i].text
        if word.startswith("-") and len(word) > 1:
            name, eq, value = word.partition("=")
            if not eq and name in _PIP_VALUE_FLAGS and i + 1 < len(args):
                flags[name] = args[i + 1]
                i += 2
                continue
            if name in {"--from", "--spec"} and eq and not args[i].quoted:
                flags[name] = Token(value, args[i].start + len(name) + 1, args[i].end, "", args[i].plain)
            else:
                flags[name] = True
            i += 1
            continue
        return [args[i]], flags
    return [], flags


# ------------------------------------------------------------------ git / gh


def _git_clone(args: list[Token], attempt: Attempt) -> None:
    positional, flags = _positionals(args, {"-b", "--branch", "--depth", "-o", "--origin",
                                            "-c", "--config", "--reference", "-j", "--jobs",
                                            "--filter", "--template", "-u", "--upload-pack",
                                            "--separate-git-dir", "--shallow-since",
                                            "--shallow-exclude", "--revision"})
    if not positional:
        return
    url = positional[0].text
    gh = _GITHUB_URL.fullmatch(url) or re.fullmatch(
        r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?()", url)
    if not gh or not positional[0].plain:
        attempt.unscannable = ("it clones from a host Trojaino does not support"
                               if "://" in url or "@" in url else None)
        if attempt.unscannable is None and not _local_path(url):
            attempt.unscannable = "the repository location is not recognised"
        return
    ref = flags.get("--branch") or flags.get("-b") or flags.get("--revision") or None
    attempt.targets.append(Target("github", f"{gh[1]}/{gh[2]}", ref or None, None))


# ------------------------------------------------------------------ claude


def _claude(args: list[Token], attempt: Attempt, tool: str) -> None:
    words = [t.text for t in args]
    if words[:2] == ["mcp", "add"]:
        rest = args[2:]
        positional, flags = _positionals(
            [t for t in rest], {"-t", "--transport", "-s", "--scope", "-e", "--env",
                                "-H", "--header", "--client-id", "--callback-port"})
        transport = flags.get("--transport") or flags.get("-t") or "stdio"
        if transport in {"http", "sse"}:
            attempt.unscannable = "it connects Claude to a remote MCP server"
            return
        if "--" in [t.text for t in rest]:
            command = rest[[t.text for t in rest].index("--") + 1:]
        else:
            command = positional[1:]
        _classify_argv(command, attempt, tool)
        if not attempt.targets and attempt.unscannable is None:
            attempt.unscannable = "it adds an MCP server Trojaino cannot identify"
        return
    if words[:2] == ["mcp", "add-json"] and len(args) >= 4:
        try:
            config = json.loads(args[3].text)
            argv = [config.get("command", "")] + list(config.get("args", []))
        except (ValueError, AttributeError, TypeError):
            attempt.unscannable = "it adds an MCP server Trojaino cannot identify"
            return
        if config.get("type") in {"http", "sse"} or config.get("url"):
            attempt.unscannable = "it connects Claude to a remote MCP server"
            return
        _classify_argv([Token(str(a), 0, 0, "", True) for a in argv if a], attempt, tool)
        if not attempt.targets and attempt.unscannable is None:
            attempt.unscannable = "it adds an MCP server Trojaino cannot identify"
        return
    if words[:2] == ["plugin", "install"]:
        positional, _ = _positionals(args[2:], {"-s", "--scope"})
        for token in positional:
            attempt.targets.append(Target("plugin", token.text, None, None))
        return
    if words[:3] == ["plugin", "marketplace", "add"]:
        positional, _ = _positionals(args[3:], {"-s", "--scope"})
        if not positional:
            return
        source = positional[0].text
        gh = _GITHUB_URL.fullmatch(source) or re.fullmatch(
            r"(?:https://github\.com/)?([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?(?:#(.+))?", source)
        if _local_path(source):
            attempt.targets.append(Target("local", source, None, None))
        elif gh:
            attempt.targets.append(Target("github", f"{gh[1]}/{gh[2]}", gh[3], None))
        else:
            attempt.unscannable = "it adds a marketplace from a location Trojaino cannot fetch"


# --------------------------------------------------------------- dispatcher

_UNSCANNABLE_INSTALLERS = {
    "winget": {"install", "add"}, "choco": {"install"}, "scoop": {"install"},
    "brew": {"install", "reinstall"}, "port": {"install"}, "apt": {"install"},
    "apt-get": {"install"}, "dnf": {"install"}, "yum": {"install"}, "pacman": {"-S", "-U"},
    "zypper": {"install", "in"}, "snap": {"install"}, "flatpak": {"install"},
    "cargo": {"install"}, "go": {"install", "get"}, "gem": {"install"},
    "composer": {"require", "global"}, "dotnet": {"tool"}, "conda": {"install", "create"},
    "mamba": {"install", "create"}, "docker": {"pull"}, "podman": {"pull"},
}
_UNSCANNABLE_ALWAYS = {"msiexec": "it runs a Windows installer",
                       "install-module": "it installs a PowerShell module",
                       "install-package": "it installs a PowerShell package",
                       "install-script": "it installs a PowerShell script",
                       "add-appxpackage": "it installs a Windows app package"}
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "python", "python3", "py", "node",
           "iex", "invoke-expression", "pwsh", "powershell", "perl", "ruby"}
_DOWNLOADERS = {"curl", "wget", "iwr", "invoke-webrequest", "irm", "invoke-restmethod"}


def _classify_argv(tokens: list[Token], attempt: Attempt, tool: str) -> None:
    tokens = _strip_prefix(tokens)
    if not tokens:
        return
    prog = _program(tokens[0].text)
    args = tokens[1:]
    words = [t.text for t in args]
    first = words[0].lower() if words else ""

    if prog in {"npx", "bunx"}:
        _npx(args, attempt)
    elif prog == "pnpx":
        _npx(args, attempt)
    elif prog in {"npm", "pnpm", "yarn", "bun"}:
        sub_index = 0
        while sub_index < len(args) and args[sub_index].text.startswith("-"):
            option, eq, _ = args[sub_index].text.partition("=")
            sub_index += 2 if option in _NPM_VALUE_FLAGS and not eq else 1
        sub = args[sub_index].text if sub_index < len(args) else ""
        # Include global options so registry/source overrides are not lost.
        rest = args[:sub_index] + args[sub_index + 1:]
        if prog == "yarn" and sub == "global" and rest[:1] and rest[0].text == "add":
            sub, rest = "add", rest[1:]
        if sub in {"exec", "x", "dlx"}:
            _npx(rest, attempt)
        elif sub in _NPM_INSTALL:
            _npm_packages(rest, attempt)
    elif prog in {"pip", "pip3"} or re.fullmatch(r"pip3\.\d+", prog):
        index = 0
        while index < len(args) and args[index].text.startswith("-"):
            option, eq, _ = args[index].text.partition("=")
            index += 2 if option in _PIP_VALUE_FLAGS and not eq else 1
        if index < len(args) and args[index].text == "install":
            _pip_packages(args[:index] + args[index + 1:], attempt)
    elif prog in {"python", "python3", "py"} or re.fullmatch(r"python3\.\d+", prog):
        if "-m" in words:
            i = words.index("-m")
            if words[i + 1:i + 2] == ["pip"]:
                _classify_argv(args[i + 1:], attempt, tool)
            elif words[i + 1:i + 2] == ["pipx"]:
                _classify_argv(args[i + 1:], attempt, tool)
    elif prog == "uv":
        if words[:2] == ["pip", "install"]:
            _pip_packages(args[2:], attempt)
        elif first == "add":
            _pip_packages(args[1:], attempt)
        elif words[:2] in (["tool", "install"], ["tool", "run"]):
            _uvx(args[2:], attempt, at_style=words[1] == "run")
        elif first == "run" and any(w.split("=", 1)[0] in {"--with", "--with-editable"} for w in words):
            attempt.unscannable = "additional runner packages cannot be bound reliably; review the install"
    elif prog == "uvx":
        _uvx(args, attempt, at_style=True)
    elif prog == "pipx":
        if first in {"install", "run"}:
            _uvx(args[1:], attempt)
            if first == "run" and not any(t.text.startswith("--spec") for t in args):
                attempt.targets = [replace(t, pin_style="unbound") for t in attempt.targets]
        elif first == "inject" and len(args) > 2:
            _pip_packages(args[2:], attempt)
    elif prog == "git" and first == "clone":
        _git_clone(args[1:], attempt)
    elif prog == "gh" and words[:2] == ["repo", "clone"] and len(args) > 2:
        repo = args[2].text
        if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            args = [replace(args[2], text="https://github.com/" + repo)] + args[3:]
        else:
            args = args[2:]
        _git_clone(args, attempt)
    elif prog == "claude":
        _claude(args, attempt, tool)
    elif prog in _UNSCANNABLE_INSTALLERS:
        if first in _UNSCANNABLE_INSTALLERS[prog] or (prog == "pacman" and first.startswith("-s")):
            attempt.unscannable = f"it installs software with {prog}, which Trojaino cannot scan"
    elif prog in _UNSCANNABLE_ALWAYS:
        attempt.unscannable = _UNSCANNABLE_ALWAYS[prog]
    elif prog in {"start-process", "saps", "start"} and any(
            w.lower().endswith((".exe", ".msi", ".msix")) for w in words):
        attempt.unscannable = "it runs a downloaded installer"
    elif tokens[0].text.lower().endswith((".exe", ".msi", ".msix", ".pkg", ".dmg", ".appimage")):
        attempt.unscannable = "it runs a downloaded installer"
    elif prog in {"sh", "bash", "zsh", "pwsh", "powershell", "cmd"}:
        # bash -c "npm install x" and friends: look inside the quoted command.
        flags = {"-c", "-command", "/c", "-Command"}
        for i, word in enumerate(words[:-1]):
            if word in flags:
                inner_tool = "PowerShell" if prog in {"pwsh", "powershell"} else "Bash"
                for inner in detect(args[i + 1].text, inner_tool, pin=False):
                    attempt.targets.extend(inner.targets)
                    attempt.unscannable = attempt.unscannable or inner.unscannable
                break


def detect(command: str, tool: str = "Bash", pin: bool = True) -> list[Attempt]:
    """Every install attempt in a Bash or PowerShell command."""
    try:
        segments = tokenize(command, tool)
    except ValueError:
        lowered = command.lower()
        if any(word in lowered for word in ("install", "npx", "uvx", "clone", "mcp add")):
            return [Attempt(command, unscannable="the command could not be read reliably")]
        return []
    attempts: list[Attempt] = []
    for tokens in segments:
        attempt = Attempt(" ".join(t.text for t in tokens))
        _classify_argv(tokens, attempt, tool)
        if not pin:
            attempt.targets = [Target(t.ecosystem, t.name, t.spec, None, t.extras, t.alias, t.subdir)
                               for t in attempt.targets]
        if attempt.targets or attempt.unscannable:
            attempts.append(attempt)
    # A download piped into an interpreter: curl ... | sh, iwr ... | iex.
    for left, right in zip(segments, segments[1:]):
        left_prog = _program(_strip_prefix(left)[0].text) if _strip_prefix(left) else ""
        right_prog = _program(_strip_prefix(right)[0].text) if _strip_prefix(right) else ""
        if left_prog in _DOWNLOADERS and right_prog in _SHELLS:
            attempts.append(Attempt(command, unscannable="it downloads a script and runs it"))
    if re.search(r"\b(iex|invoke-expression)\b[\s(]*[\(\$]?\s*\(?\s*(irm|iwr|invoke-restmethod|invoke-webrequest|new-object)\b",
                 command, re.I) and not any("downloads a script" in (a.unscannable or "") for a in attempts):
        attempts.append(Attempt(command, unscannable="it downloads a script and runs it"))
    return attempts


# --------------------------------------------------------- configuration files

_CONFIG_NAMES = {".mcp.json", ".claude.json", "claude_desktop_config.json"}


def config_change(tool_name: str, tool_input: dict) -> str | None:
    """A reason when a file edit changes which MCP servers or plugins Claude loads."""
    if tool_name not in {"Write", "Edit", "MultiEdit"}:
        return None
    path = str(tool_input.get("file_path", "")).replace("\\", "/")
    name = path.rsplit("/", 1)[-1].lower()
    if name in _CONFIG_NAMES:
        return "it changes which MCP servers Claude loads"
    if re.search(r"(^|/)\.claude/settings(\.local)?\.json$", path, re.I):
        text = json.dumps(tool_input).lower()
        if any(key in text for key in ("mcpservers", "enabledplugins", "extraknownmarketplaces",
                                       "enabledmcpjsonservers", "hooks")):
            return "it changes which plugins, MCP servers or hooks Claude loads"
    return None
