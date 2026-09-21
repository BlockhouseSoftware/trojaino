"""The install gate: decide what happens when Claude tries to install something.

For every install attempt the detector recognises:

- clean scan         -> Trojaino steps aside, pinning the exact version it
                        scanned. Claude's normal permission rules still apply.
- CAUTION            -> Claude's permission prompt, with the findings.
- DO NOT RUN         -> blocked.
- cannot be scanned  -> Claude's permission prompt, with the reason.

Everything that is not an install passes through without a word. The gate
never raises into Claude Code: any internal failure becomes a permission
prompt, never a silent pass and never a blanket block.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time

from trojaino import __version__
from trojaino.install_detect import Attempt, Target, config_change, detect
from trojaino import registry

GATE_DEADLINE_SECONDS = 90
CLEAN = "NO CRITICAL RISKS FOUND"


@dataclass
class Outcome:
    label: str
    verdict: str | None = None          # scanner verdict, or None when not scanned
    problem: str | None = None          # why it could not be scanned
    blocked: str | None = None          # why it must not be installed at all
    files: int = 0
    findings: list = field(default_factory=list)
    compiled: list = field(default_factory=list)
    report: str | None = None
    pin: str | None = None              # replacement text for the target's token
    target: Target | None = None


# ---------------------------------------------------------------- state


def state_directory() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        return base / "trojaino"
    return Path.home() / ".local" / "state" / "trojaino"


def _private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def _cache_path(key: list) -> Path:
    digest = hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()
    return state_directory() / "verdicts" / f"{digest}.json"


def _cached(key: list) -> dict | None:
    try:
        path = _cache_path(key)
        if path.is_file() and not path.is_symlink() and path.stat().st_size < 1_000_000:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("key") == key:
                return data
    except (OSError, ValueError):
        pass
    return None


def _remember(key: list, outcome: Outcome) -> None:
    try:
        folder = _private_dir(state_directory() / "verdicts")
        (folder / _cache_path(key).name).write_text(json.dumps({
            "key": key, "verdict": outcome.verdict, "files": outcome.files,
            "findings": outcome.findings, "report": outcome.report}), encoding="utf-8")
    except OSError:
        pass


# ---------------------------------------------------------------- scanning


def _identity() -> str:
    from trojaino.preflight import scanner_identity
    return scanner_identity()


def scan_files(label: str, files: dict, compiled: list) -> Outcome:
    """Write staged text to a private folder, scan it in an isolated worker, report."""
    from trojaino.preflight import scan_path
    outcome = Outcome(label, compiled=list(compiled))
    reports = _private_dir(state_directory() / "reports")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9._@=-]+", "_", label)[:40]  # Windows paths top out at 260 characters
    job = Path(tempfile.mkdtemp(prefix=f"{stamp}-{safe}-", dir=reports))
    staged = job / "source"
    try:
        staged.mkdir(mode=0o700)
        for name, data in files.items():
            destination = staged.joinpath(*name.split("/"))
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with destination.open("xb") as handle:
                handle.write(data)
        if not files:
            outcome.verdict = CLEAN
            outcome.files = 0
        else:
            report = scan_path(staged, profile="package")
            raw = report.raw_report
            (job / "scanner.json").write_text(json.dumps(raw, indent=2, ensure_ascii=True) + "\n")
            outcome.report = str(job / "scanner.json")
            outcome.files = raw.get("files_scanned", 0)
            if raw.get("complete") is not True:
                outcome.problem = "the scan could not finish within Trojaino's limits"
            else:
                outcome.verdict = raw.get("verdict")
                outcome.findings = [
                    {"rule": f.get("id") if isinstance(f, dict) else f.id,
                     "severity": f.get("severity") if isinstance(f, dict) else f.severity,
                     "file": f.get("file") if isinstance(f, dict) else f.file,
                     "line": f.get("line") if isinstance(f, dict) else f.line,
                     "title": f.get("title") if isinstance(f, dict) else getattr(f, "title", "")}
                    for f in raw.get("findings", [])][:20]
    except Exception:
        outcome.problem = "Trojaino's scanner failed on this package"
    finally:
        shutil.rmtree(staged, ignore_errors=True)
    return outcome


def _scan_artifact(artifact: registry.Artifact) -> Outcome:
    key = [artifact.ecosystem, artifact.name, artifact.version, artifact.digest,
           artifact.subdir, _identity()]
    cached = _cached(key)
    if cached:
        return Outcome(artifact.label, verdict=cached["verdict"], files=cached["files"],
                       findings=cached["findings"], report=cached["report"])
    try:
        staged = registry.unpack(artifact, registry.download(artifact))
    except registry.Refused as exc:
        if "checksum" in str(exc) or "unsafe" in str(exc) or "collide" in str(exc):
            return Outcome(artifact.label, blocked=str(exc))
        return Outcome(artifact.label, problem=str(exc))
    outcome = scan_files(artifact.label, staged.files, staged.compiled)
    if outcome.verdict and not outcome.problem:
        _remember(key, outcome)
    return outcome


def _local_files(path: Path) -> tuple[dict, list]:
    """Read a local folder as data, never following links."""
    files: dict = {}
    compiled: list = []
    total = 0
    root = path.resolve()
    if root.is_file():
        entries = [(root, root.name)]
    else:
        entries = []
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in dirnames if d not in {".git", "node_modules", ".venv", "__pycache__"}
                           and not os.path.islink(os.path.join(directory, d))]
            for filename in filenames:
                full = Path(directory) / filename
                entries.append((full, full.relative_to(root).as_posix()))
                if len(entries) > registry.MAX_ENTRIES:
                    raise registry.Unscannable("the folder has too many files for Trojaino to scan")
    for full, relative in entries:
        if full.is_symlink() or not full.is_file():
            continue
        lowered = relative.lower()
        if lowered.endswith(registry.COMPILED_SUFFIXES):
            compiled.append(relative)
            continue
        if not registry._is_code(relative):
            continue
        size = full.stat().st_size
        if size > registry.MAX_CODE_FILE_BYTES:
            raise registry.Unscannable(f"{relative} is too large for Trojaino to read")
        total += size
        if total > registry.MAX_CODE_BYTES or len(files) >= registry.MAX_FILES:
            raise registry.Unscannable("the folder is too large for Trojaino to scan")
        data = full.read_bytes()
        if data.startswith(registry._MAGIC):
            compiled.append(relative)
            continue
        files[relative] = data
    return files, compiled


# ---------------------------------------------------------------- plugins


def _config_directory() -> Path:
    configured = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(configured) if configured else Path.home() / ".claude"


def _plugin_target(spec: str) -> Target | str:
    """name@marketplace -> the source Claude Code will install from."""
    name, _, market = spec.partition("@")
    if not market:
        return "the plugin's marketplace is not named, so Trojaino cannot tell where it comes from"
    try:
        known = json.loads((_config_directory() / "plugins" / "known_marketplaces.json").read_text("utf-8"))
        record = known[market]
        location = Path(record["installLocation"])
        catalog = json.loads((location / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
        entry = next(p for p in catalog["plugins"] if p.get("name") == name)
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        return f"Trojaino could not find {spec} in a marketplace Claude already knows"
    source = entry.get("source")
    if isinstance(source, str):
        if source.startswith("./") or not re.match(r"[a-z]+:", source):
            return Target("local", str((location / source).resolve()), None, None)
        return "the plugin comes from a source Trojaino does not support"
    if not isinstance(source, dict):
        return "the plugin's source is not recognised"
    kind = source.get("source")
    ref = source.get("sha") or source.get("ref")
    if kind == "github" and source.get("repo"):
        return Target("github", source["repo"], ref, None, subdir=source.get("path", ""))
    if kind in {"url", "git-subdir"}:
        m = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?/?",
                         str(source.get("url", "")))
        if m:
            return Target("github", f"{m[1]}/{m[2]}", ref, None, subdir=source.get("path", ""))
    if kind == "npm" and source.get("package"):
        return Target("npm", source["package"], source.get("version"), None)
    return "the plugin comes from a source Trojaino does not support"


# ---------------------------------------------------------------- one target


def _pin_text(target: Target, artifact: registry.Artifact) -> str | None:
    if target.token is None or target.token.end <= target.token.start:
        return None
    if target.ecosystem == "npm":
        return f"{target.alias}{artifact.name}@{artifact.version}"
    if target.ecosystem == "pypi":
        if target.pin_style == "@":
            return f"{artifact.name}{target.extras}@{artifact.version}"
        return f"{artifact.name}{target.extras}=={artifact.version}"
    return None


def evaluate(target: Target, cwd: str | None) -> Outcome:
    try:
        if target.ecosystem == "plugin":
            resolved = _plugin_target(target.name)
            if isinstance(resolved, str):
                return Outcome(target.name, problem=resolved)
            outcome = evaluate(resolved, cwd)
            outcome.label = f"{target.name} ({outcome.label})"
            return outcome
        if target.ecosystem == "local":
            path = Path(os.path.expanduser(target.name))
            if not path.is_absolute():
                path = Path(cwd or os.getcwd()) / path
            if not path.exists():
                return Outcome(target.name, problem=f"{target.name} does not exist")
            files, compiled = _local_files(path)
            return scan_files(path.name or str(path), files, compiled)
        if target.ecosystem == "npm":
            artifact = registry.resolve_npm(target.name, target.spec)
        elif target.ecosystem == "pypi":
            artifact = registry.resolve_pypi(target.name, target.spec)
        elif target.ecosystem == "github":
            artifact = registry.resolve_github(target.name, target.spec, target.subdir)
        else:
            return Outcome(target.name, problem="the source is not supported")
        outcome = _scan_artifact(artifact)
        outcome.target = target
        outcome.pin = _pin_text(target, artifact)
        return outcome
    except registry.Unscannable as exc:
        return Outcome(target.name, problem=str(exc))
    except Exception:
        return Outcome(target.name, problem="Trojaino hit an internal error checking it")


# ---------------------------------------------------------------- the decision


def _quote(text: str, token, tool: str) -> str:
    if token.quoted:
        return token.quoted + text + token.quoted
    if tool == "PowerShell" and (text.startswith("@") or "[" in text):
        return "'" + text + "'"
    if "[" in text or "<" in text or ">" in text:
        return "'" + text + "'"
    return text


def _describe(outcome: Outcome) -> str:
    if outcome.blocked:
        return f"{outcome.label}: {outcome.blocked}"
    if outcome.problem:
        return f"{outcome.label}: not scanned, because {outcome.problem}"
    text = f"{outcome.label}: {outcome.verdict} ({outcome.files} files scanned)"
    if outcome.findings:
        top = "; ".join(f"{f['rule']} in {f['file']}:{f['line']}" for f in outcome.findings[:3])
        text += f" - {top}"
    if outcome.compiled:
        shown = ", ".join(outcome.compiled[:3])
        text += f"; it also contains compiled code Trojaino cannot read ({shown})"
    if outcome.report:
        text += f". Report: {outcome.report}"
    return text


def decide(command: str, tool: str, tool_input: dict, cwd: str | None) -> dict | None:
    """The hook's answer for one command, or None to stay out of the way."""
    attempts = detect(command, tool)
    if not attempts:
        return None
    deadline = time.monotonic() + GATE_DEADLINE_SECONDS
    outcomes: list[Outcome] = []
    unscannable: list[str] = []
    for attempt in attempts:
        if attempt.unscannable and not attempt.targets:
            unscannable.append(f"{attempt.command}: {attempt.unscannable}")
            continue
        if attempt.unscannable:
            unscannable.append(f"{attempt.command}: {attempt.unscannable}")
        for target in attempt.targets:
            if time.monotonic() > deadline:
                outcomes.append(Outcome(target.name, problem="Trojaino ran out of time checking it"))
                continue
            outcomes.append(evaluate(target, cwd))

    blocked = [o for o in outcomes if o.blocked or o.verdict == "DO NOT RUN"]
    if blocked:
        return _answer("deny", "Trojaino blocked this install. " + " | ".join(_describe(o) for o in blocked)
                       + ". Do not retry or work around this; show the user the report.")

    doubtful = [o for o in outcomes if o.problem or o.verdict != CLEAN or o.compiled]
    if doubtful or unscannable:
        parts = unscannable + [_describe(o) for o in doubtful]
        return _answer("ask", "Trojaino could not clear this install. " + " | ".join(parts)
                       + ". Decide whether to allow it.")

    # Everything clean: step aside, pinning exactly what was scanned.
    summary = "; ".join(_describe(o) for o in outcomes)
    note = (f"Trojaino {__version__} scanned this install: {summary}. "
            "Only the named packages were scanned, not their dependencies.")
    rewritten = command
    for outcome in sorted((o for o in outcomes if o.pin and o.target and o.target.token),
                          key=lambda o: o.target.token.start, reverse=True):
        token = outcome.target.token
        rewritten = rewritten[:token.start] + _quote(outcome.pin, token, tool) + rewritten[token.end:]
    result = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}
    if rewritten != command:
        result["hookSpecificOutput"]["updatedInput"] = dict(tool_input, command=rewritten)
    return result


def _answer(decision: str, reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                   "permissionDecisionReason": reason[:4000]}}


def handle(event: dict) -> dict | None:
    """Entry point for both hook events. Never raises."""
    try:
        name = event.get("hook_event_name")
        if name == "SessionStart":
            return session_start()
        if name != "PreToolUse":
            return None
        tool = event.get("tool_name")
        tool_input = event.get("tool_input") or {}
        if tool in {"Bash", "PowerShell"}:
            command = tool_input.get("command")
            if not isinstance(command, str) or len(command) > 20000:
                return None
            return decide(command, tool, tool_input, event.get("cwd"))
        reason = config_change(tool, tool_input)
        if reason:
            return _answer("ask", f"Trojaino: this edit {reason}. Trojaino cannot vet new MCP servers "
                                  "or plugins added this way. Decide whether to allow it.")
        return None
    except Exception:
        return _answer("ask", "Trojaino hit an internal error checking this command. Decide whether to allow it.")


def scan_command() -> str:
    import sys
    entry = getattr(sys.modules["trojaino"], "_sealed_entry", None) or str(
        Path(__file__).resolve().parent.parent / "plugins" / "trojaino" / "scripts" / "preflight.py")
    return f'python3 -I -S "{str(entry).replace(chr(92), "/")}" scan'


def session_start() -> dict:
    from trojaino.freshness import session_reminder
    try:
        reminder = session_reminder(__version__)
    except Exception:
        reminder = ""
    text = (f"Trojaino {__version__} install gate is active. When Claude installs or adds software "
            "(npm, npx, pip, uvx, pipx, git clone, claude mcp add, claude plugin install), Trojaino "
            "scans that exact package first. Clean packages are pinned to the scanned version and "
            "continue; CAUTION results and anything it cannot scan go to the user to decide; "
            "DO NOT RUN results are blocked and must not be worked around. Only the named package is "
            "scanned, not its dependencies. To scan something without installing it, run: "
            f"{scan_command()} SOURCE (SOURCE is npm:NAME, pypi:NAME, a GitHub URL or a path).")
    if reminder:
        text += " " + reminder
    return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}


def scan_source(source: str, cwd: str | None = None) -> dict:
    """Manual scan for the /trojaino:scan skill: npm:NAME[@V], pypi:NAME[==V], a GitHub URL or a path."""
    if source.startswith("npm:"):
        name, _, spec = source[4:].rpartition("@") if source[4:].count("@") > (1 if source[4:].startswith("@") else 0) \
            else (source[4:], "", "")
        target = Target("npm", (name or source[4:]).lower(), spec or None, None)
    elif source.startswith("pypi:"):
        m = re.fullmatch(r"([A-Za-z0-9._-]+)(\[[^\]]*\])?(.*)", source[5:])
        if not m:
            return {"result": "not scanned", "reason": "the package name is not recognised"}
        target = Target("pypi", re.sub(r"[-_.]+", "-", m[1]).lower(), m[3].strip() or None, None)
    elif source.startswith(("https://github.com/", "github:")):
        m = re.fullmatch(r"(?:https://github\.com/|github:)([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)"
                         r"(?:\.git)?(?:/tree/([^/]+)(?:/(.*))?)?(?:@(.+))?/?", source)
        if not m:
            return {"result": "not scanned", "reason": "the GitHub address is not recognised"}
        target = Target("github", f"{m[1]}/{m[2]}", m[3] or m[5], None, subdir=m[4] or "")
    else:
        target = Target("local", source, None, None)
    outcome = evaluate(target, cwd)
    return {"result": outcome.verdict or ("blocked" if outcome.blocked else "not scanned"),
            "summary": _describe(outcome), "report": outcome.report,
            "findings": outcome.findings, "compiled_code": outcome.compiled,
            "dependencies_scanned": False}
