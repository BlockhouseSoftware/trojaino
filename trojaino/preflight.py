"""Local pre-execution pilot; separate from the scanner's public contract."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import signal
import hashlib
import io
import gzip
import unicodedata
import re
import tarfile
import urllib.request
import json
from pathlib import Path
import os
import stat
import shlex
import time
import tempfile

import subprocess
import sys
from types import SimpleNamespace

SCAN_TIMEOUT = 10.0


def trusted_environment():
    if os.name == "nt":
        from trojaino.preflight_windows import system_directory
        system = system_directory()
        return {"SystemRoot": str(Path(system).parent), "PATH": system,
                "LANG": "C.UTF-8"}
    return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


def isolated_operation(name, args, timeout=20, stdin=subprocess.DEVNULL):
    """A killable trusted process, not an uninterruptible Windows timer thread."""
    worker = getattr(sys.modules['trojaino'], '_sealed_worker', None)
    if worker is not None:
        try:
            return worker(name, args, timeout=timeout, stdin=stdin if name == 'hook_input' else None)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise Denied('operation_error_or_timeout') from exc
    trusted = str(Path(__file__).resolve().parent.parent)
    code = ("import sys; sys.path.insert(0,sys.argv[1]); "
            "from trojaino.preflight_process import main; "
            "sys.argv=sys.argv[1:]; main()")
    environment = trusted_environment()
    if "TROJAINO_NODE" in os.environ:
        environment["TROJAINO_NODE"] = os.environ["TROJAINO_NODE"]
    with tempfile.TemporaryFile() as output:
        try:
            subprocess.run([sys.executable, "-I", "-S", "-c", code, trusted,
                            json.dumps([name, args])], cwd=trusted, stdin=stdin,
                           stdout=output, stderr=subprocess.DEVNULL,
                           env=environment, timeout=timeout, check=True)
            output.seek(0)
            data = output.read(5_000_001)
            if len(data) > 5_000_000:
                raise ValueError("worker_output_limit")
            return json.loads(data)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise Denied("operation_error_or_timeout") from exc


def scan_path(target, profile="default"):
    """Isolated trusted worker: target cwd/PYTHONPATH/site hooks never import."""
    worker = getattr(sys.modules['trojaino'], '_sealed_worker', None)
    if worker is not None:
        report = worker('scan_path', [str(target)], timeout=SCAN_TIMEOUT)
        report['raw_report'] = dict(report)
        report['findings'] = [SimpleNamespace(**f) for f in report['findings']]
        return SimpleNamespace(**report)
    trusted = str(Path(__file__).resolve().parent.parent)
    code = (
        "import sys,json; sys.path.insert(0,sys.argv[1]); "
        "from trojaino.scanner import scan_path,ScanLimits; "
        "r=scan_path(sys.argv[2],profile='default',limits=ScanLimits(max_elapsed_seconds=8)); "
        "print(json.dumps(r.to_dict()))"
    )
    with tempfile.TemporaryFile() as output:
        subprocess.run([sys.executable, "-I", "-S", "-c", code, trusted, str(target)],
                       cwd=trusted, stdin=subprocess.DEVNULL, stdout=output,
                       stderr=subprocess.DEVNULL, timeout=SCAN_TIMEOUT, check=True,
                       env=trusted_environment())
        output.seek(0)
        data = output.read(5_000_001)
    if len(data) > 5_000_000:
        raise Denied("scanner_error_or_timeout")
    report = json.loads(data)
    report["raw_report"] = dict(report)
    report["findings"] = [SimpleNamespace(**f) for f in report["findings"]]
    return SimpleNamespace(**report)

from trojaino.file_utils import should_scan
from trojaino import __version__
from trojaino.contract import REPORT_SCHEMA_VERSION, RULE_PACK_ID, RULE_PACK_VERSION


def scanner_identity():
    sealed_identity = getattr(sys.modules['trojaino'], '_sealed_identity', None)
    if sealed_identity is not None:
        return sealed_identity
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    digest.update(json.dumps([__version__, RULE_PACK_ID, RULE_PACK_VERSION]).encode())
    metadata = root.parent / "pyproject.toml"
    if metadata.is_file():
        digest.update(metadata.read_bytes())
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


class Denied(Exception):
    pass


MAX_FILES = 5000
MAX_ENTRIES = 20000
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 20_000_000
MAX_DEPTH = 50


def snapshot(root):
    """Bounded openat traversal. Never follow a link or open a device/FIFO."""
    if os.name == "nt":
        from trojaino.preflight_windows import snapshot as native_snapshot
        return native_snapshot(root)
    root = Path(root)
    if not root.is_absolute() or ".." in root.parts:
        raise Denied("unsafe_source")
    files = {}
    entries = total = 0
    deadline = time.monotonic() + 5

    def walk(fd, prefix, depth):
        nonlocal entries, total
        if depth > MAX_DEPTH:
            raise Denied("staging_limit")
        with os.scandir(fd) as iterator:
            for entry in iterator:
                entries += 1
                if entries > MAX_ENTRIES or time.monotonic() > deadline:
                    raise Denied("staging_limit")
                rel = prefix / entry.name
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                    try:
                        walk(child, rel, depth + 1)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(info.st_mode):
                    if len(files) >= MAX_FILES or info.st_size > MAX_FILE_BYTES:
                        raise Denied("staging_limit")
                    child = os.open(entry.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                    try:
                        opened = os.fstat(child)
                        if not stat.S_ISREG(opened.st_mode) or not opened.st_mode & 0o444:
                            raise Denied("unsafe_source")
                        with os.fdopen(os.dup(child), "rb") as stream:
                            data = stream.read(MAX_FILE_BYTES + 1)
                        after = os.fstat(child)
                        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                            raise Denied("unsafe_source")
                    finally:
                        os.close(child)
                    total += len(data)
                    if len(data) > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                        raise Denied("staging_limit")
                    files[rel.as_posix()] = data
                else:
                    raise Denied("unsafe_source")

    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        walk(fd, Path(), 0)
    finally:
        os.close(fd)
    return files


def github_archive_url(source):
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_-]+)/([A-Za-z0-9_.-]+)/tree/([0-9a-f]{40})", source)
    if not match or match[2] in {".", ".."}:
        raise Denied("unsafe_source")
    return f"https://codeload.github.com/{match[1]}/{match[2]}/tar.gz/{match[3]}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_github(source):
    url = github_archive_url(source)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(url, headers={"User-Agent": "trojaino-preflight/1", "Accept-Encoding": "identity"})
    deadline = time.monotonic() + 8
    with opener.open(request, timeout=3) as response:
        if response.status != 200 or response.url != url:
            raise Denied("acquisition_error")
        chunks = bytearray()
        while True:
            if time.monotonic() > deadline:
                raise Denied("acquisition_error")
            chunk = response.read(65536)
            if not chunk:
                break
            chunks.extend(chunk)
            if len(chunks) > 10_000_000:
                raise Denied("staging_limit")
    return bytes(chunks)


def stage_archive(data, staged):
    # Bound decompressed TAR bytes before tarfile processes PAX metadata.
    if len(data) > 10_000_000:
        raise Denied("staging_limit")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
            raw = compressed.read(25_000_001)
        if len(raw) > 25_000_000:
            raise Denied("staging_limit")
        files = {}
        seen = set()
        spellings = {}
        root = None
        total = entries = 0
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
            for member in archive:
                entries += 1
                parts = member.name.rstrip("/").split("/")
                if (entries > MAX_ENTRIES or len(parts) > MAX_DEPTH + 1):
                    raise Denied("staging_limit")
                from trojaino.preflight_paths import valid_component
                if (any(not valid_component(p) for p in parts) or "\\" in member.name
                        or any(ord(c) < 32 for c in member.name)
                        or not (member.isdir() or member.isfile()) or member.issparse()):
                    raise Denied("unsafe_archive")
                for depth in range(1, len(parts) + 1):
                    spelling = "/".join(parts[:depth])
                    normalized = unicodedata.normalize("NFC", spelling).casefold()
                    if normalized in spellings and spellings[normalized] != spelling:
                        raise Denied("unsafe_archive")
                    spellings[normalized] = spelling
                key = unicodedata.normalize("NFC", member.name.rstrip("/")).casefold()
                if key in seen or (root is not None and root != parts[0]):
                    raise Denied("unsafe_archive")
                seen.add(key)
                root = parts[0]
                if member.isdir():
                    continue
                if len(parts) < 2:
                    raise Denied("unsafe_archive")
                total += member.size
                if (member.size > MAX_FILE_BYTES or member.size < 0
                        or total > MAX_TOTAL_BYTES or len(files) >= MAX_FILES):
                    raise Denied("staging_limit")
                stream = archive.extractfile(member)
                if stream is None:
                    raise Denied("unsafe_archive")
                files["/".join(parts[1:])] = stream.read(MAX_FILE_BYTES + 1)
        if os.name == "nt":
            from trojaino.preflight_windows import write_tree
            write_tree(staged, files)
            return
        staged.mkdir(mode=0o700)
        for name, content in files.items():
            dest = staged / name
            dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with dest.open("xb") as output:
                output.write(content)
            dest.chmod(0o600)
    except (tarfile.TarError, OSError, EOFError, ValueError) as exc:
        raise Denied("unsafe_archive") from exc


def stage_local(source, staged):
    files = snapshot(source)
    if os.name == "nt":
        from trojaino.preflight_windows import write_tree
        write_tree(staged, files)
        return
    staged.mkdir(mode=0o700)
    for name, data in files.items():
        dest = staged / name
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        dest.write_bytes(data)
        dest.chmod(0o600)


def tree_digest(root):
    digest = hashlib.sha256()
    for name, data in sorted(snapshot(root).items()):
        digest.update(json.dumps([name, len(data)]).encode())
        digest.update(b"\0" + data)
    return digest.hexdigest()


def verify(receipt_path):
    try:
        path = Path(receipt_path)
        if os.name == "nt":
            from trojaino.preflight_windows import read_locked
            receipt = json.loads(read_locked(receipt_path, 5_000_000))
        else:
            if path.is_symlink() or path.stat().st_size > 5_000_000:
                raise Denied("invalid_receipt")
            receipt = json.loads(path.read_text())
        if (receipt["decision"] != "permit" or receipt["profile"] != "default"
                or receipt["scanner_identity"] != scanner_identity()
                or receipt["digest"] != tree_digest(receipt["staged_path"])):
            raise Denied("receipt_mismatch")
        fresh = gate(receipt["staged_path"], path.parent.parent)
        if fresh.get("digest") != receipt["digest"]:
            raise Denied("receipt_mismatch")
        return fresh
    except Exception:
        return {"decision": "deny", "reason": "invalid_or_changed_receipt"}


def command_prefix(tool):
    sealed_entry = getattr(sys.modules['trojaino'], '_sealed_entry', None)
    entry = (Path(sealed_entry) if sealed_entry else
             Path(__file__).resolve().parent.parent / "plugins/trojaino/scripts/preflight.py")
    values = [sys.executable, "-I", "-S", str(entry)]
    if os.name == "nt" and tool == "Bash":
        values = [v.replace("\\", "/") for v in values]
    return values


def format_command(argv, tool):
    if tool == "PowerShell":
        # Reject the entire typographic quote family, including PowerShell's
        # smart delimiters. ASCII apostrophe doubling alone is not sufficient.
        if any(any('\u2018' <= c <= '\u201f' for c in arg) for arg in argv):
            raise Denied("ambiguous_command")
        return "& " + " ".join("'" + arg.replace("'", "''") + "'" for arg in argv)
    if tool == "Bash":
        return shlex.join(argv)
    raise Denied("unsupported_tool")


def parse_command(command, tool):
    if tool == "PowerShell":
        if not re.fullmatch(r"& '(?:[^']|'')*'(?: '(?:[^']|'')*')*", command):
            raise Denied("ambiguous_command")
        argv = [token[1:-1].replace("''", "'")
                for token in re.findall(r"'(?:[^']|'')*'", command[2:])]
    else:
        argv = shlex.split(command)
    if command != format_command(argv, tool):
        raise Denied("ambiguous_command")
    return argv


def hook(event):
    try:
        if event.get("hook_event_name") == "SessionStart":
            command = format_command(command_prefix("PowerShell" if os.name == "nt" else "Bash"),
                                     "PowerShell" if os.name == "nt" else "Bash")
            grammar = ("PowerShell: use & followed by EVERY argument single-quoted; double embedded "
                       "apostrophes. Quote scan, launch and flags too. Bash alternative prefix: "
                       + format_command(command_prefix("Bash"), "Bash") + ". "
                       if os.name == "nt" else "Bash: use canonical shlex.join argument quoting. ")
            return {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": (
                "Trojaino inspection-session pilot is loaded. When asked to try or install a new MCP, "
                "plugin, or app, invoke this plugin's scan skill and inspect supported source before execution. "
                "Trusted command prefix: " + command + ". " + grammar + "Append scan SOURCE for a report-only call. "
                "Read and report the result before any separate launch RECEIPT --entry RELATIVE_ENTRY call. "
                "Only absolute source directories and exact full-commit GitHub tree URLs are supported. "
                "Do not install dependencies or activate native candidate plugins/MCPs in this session. "
                "Ordinary execution and writes are blocked in inspection mode; normal Claude permissions "
                "still apply to supported commands. This is not antivirus or an OS sandbox."
            )}}
        if event.get("hook_event_name") != "PreToolUse" or event.get("tool_name") not in {"Bash", "PowerShell"}:
            raise Denied("unsupported_tool")
        command = event["tool_input"]["command"]
        if not isinstance(command, str) or len(command) > 16000 or any(ord(c) < 32 for c in command):
            raise Denied("ambiguous_command")
        tool = event["tool_name"]
        argv = parse_command(command, tool)
        prefix = command_prefix(tool)
        if argv[:4] != prefix:
            raise Denied("ambiguous_command")
        if (len(argv) in {6, 8} and argv[4] == "scan"
                and (len(argv) == 6 or argv[6] == "--state" and Path(argv[7]).is_absolute())):
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                    "additionalContext": "Trojaino report-only scan; read its result before proposing any launch. Normal permissions apply."}}
        if len(argv) == 8 and argv[4] == "launch" and argv[6] == "--entry":
            result, _ = launch_plan(argv[5], argv[7])
            if result["decision"] == "permit":
                return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                        "additionalContext": "Trojaino receipt revalidated; launcher rechecks before execution. Normal permissions apply."}}
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                    "permissionDecisionReason": json.dumps(result, ensure_ascii=True)}}
    except Exception:
        pass
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": "Trojaino pilot: unsupported execution or activation. Use the controlled scan workflow."}}


def launch_plan(receipt_path, entry):
    result = verify(receipt_path)
    if result["decision"] != "permit":
        return result, []
    staged = Path(result["staged_path"])
    if (not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_./-]*\.(py|js|cjs|mjs)", entry)
            or ".." in Path(entry).parts or not (staged / entry).is_file()
            or tree_digest(staged) != result["digest"]):
        return {"decision": "deny", "reason": "unsupported_entry"}, []
    if entry.endswith(".py"):
        bootstrap = (
            "import sys,runpy,pathlib; root,entry=sys.argv[1:]; "
            "sys.dont_write_bytecode=True; "
            "sys.path[:0]=[str(pathlib.Path(entry).parent),root]; "
            "sys.argv=[entry]; runpy.run_path(entry,run_name='__main__')"
        )
        argv = [sys.executable, "-I", "-S", "-c", bootstrap, str(staged), str(staged / entry)]
    else:
        configured_runtime = os.environ.get("TROJAINO_NODE", "")
        if os.name == "nt":
            try:
                from trojaino.preflight_windows import locked_path
                with locked_path(configured_runtime, directory=False):
                    pass
            except (OSError, ValueError):
                return {"decision": "deny", "reason": "trusted_node_runtime_required"}, []
        runtime = Path(configured_runtime)
        if (not runtime.is_absolute() or runtime.name.lower() != ("node.exe" if os.name == "nt" else "node") or not runtime.is_file()
                or not os.access(runtime, os.X_OK) or runtime.is_relative_to(staged)):
            return {"decision": "deny", "reason": "trusted_node_runtime_required"}, []
        # Node treats '*' in a grant as a wildcard, not a literal pathname.
        if "*" in str(staged.resolve()):
            return {"decision": "deny", "reason": "unsupported_node_stage_path"}, []
        # Probe trusted runtime code only, never candidate code (including hooks).
        # Unsupported flags, missing enforcement, and probe failures fail closed.
        probe = (
            "if (!process.permission || process.permission.has('fs.read') || "
            "process.permission.has('fs.write')) process.exit(1)"
        )
        try:
            subprocess.run([str(runtime.resolve()), "--no-addons", "--permission",
                            "--input-type=commonjs", "--eval", probe],
                           cwd=str(runtime.parent) if os.name == "nt" else "/", env=trusted_environment(),
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=3, check=True)
        except (OSError, subprocess.SubprocessError):
            return {"decision": "deny", "reason": "node_permission_runtime_required"}, []
        # Restrict ordinary CJS/ESM dependency reads to the scanned tree.
        # Node permissions are not a sandbox for deliberately malicious code.
        argv = [str(runtime.resolve()), "--no-addons", "--permission",
                "--allow-fs-read=" + str(staged.resolve()), str((staged / entry).resolve())]
    return result, argv


def launch(receipt_path, entry):
    try:
        if os.name == "nt":
            result, argv = isolated_operation("launch_plan", [str(receipt_path), entry])
        else:
            with operation_timeout():
                result, argv = launch_plan(receipt_path, entry)
    except Exception:
        result, argv = {"decision": "deny", "reason": "launch_error_or_timeout"}, []
    if result["decision"] != "permit":
        print(json.dumps(result, ensure_ascii=True), file=sys.stderr, flush=True)
        return 2
    staged = Path(result["staged_path"])
    print(json.dumps(result, ensure_ascii=True), file=sys.stderr, flush=True)
    if os.name == "nt":
        from trojaino.preflight_windows import contain_process
        job = contain_process()  # lifetime is this launcher, including timeout exits
        try:
            return subprocess.run(argv, cwd=staged, env=trusted_environment(), timeout=300).returncode
        except (OSError, subprocess.SubprocessError):
            return 2
    os.chdir(staged)
    os.execve(argv[0], argv, trusted_environment())


def hook_input():
    data = sys.stdin.buffer.read(65537)
    if len(data) > 65536:
        raise Denied("invalid_input")
    event = json.loads(data)
    if not isinstance(event, dict):
        raise Denied("invalid_input")
    return hook(event)


def capabilities():
    return {"runtime_storage": "sealed-memory" if hasattr(sys.modules['trojaino'], '_sealed_identity') else "source-tree",
            "platform": sys.platform, "python": sys.version.split()[0],
            "filesystem_backend": "win32-ntfs" if os.name == "nt" else "posix-openat",
            "watchdog": "job-contained-process" if os.name == "nt" else "posix-signal",
            "hook_transport": "direct-argv; run scripts/prepare_preflight_plugin.py for literal interpreter and args",
            "command_prefixes": {tool: format_command(command_prefix(tool), tool)
                                 for tool in ("Bash", "PowerShell")},
            "authenticated_claude_verified": False,
            "filesystem_probe": "not_run; run native acceptance suite",
            "node_permission": "probed_on_each_launch", "scanner_timeout_seconds": SCAN_TIMEOUT,
            "operation_timeout_seconds": 20, "windows_launch_timeout_seconds": 300}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["capabilities"]:
        print(json.dumps(capabilities(), ensure_ascii=True))
        return 0
    if argv == ["hook"]:
        try:
            if os.name == "nt":
                result = isolated_operation("hook_input", [], stdin=sys.stdin)
            else:
                with operation_timeout():
                    result = hook_input()
        except Exception:
            result = hook({})
        print(json.dumps(result, ensure_ascii=True))
        return 0
    parser = argparse.ArgumentParser(description="Trojaino controlled preflight pilot")
    sub = parser.add_subparsers(dest="action", required=True)
    scan = sub.add_parser("scan", help="stage and report; never execute")
    scan.add_argument("source")
    scan.add_argument("--state", default=str(Path.home() / ".local/state/trojaino-pilot"))
    start = sub.add_parser("launch", help="revalidate receipt, report to stderr, exec pinned source")
    start.add_argument("receipt")
    start.add_argument("--entry", required=True)
    args = parser.parse_args(argv)
    if args.action == "launch":
        return launch(args.receipt, args.entry)
    result = gate(args.source, args.state)
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["decision"] == "permit" else 2


@contextmanager
def operation_timeout(seconds=20):
    """POSIX main-thread watchdog, shorter than the host's 30-second hook."""
    def expired(signum, frame):
        raise Denied("operation_timeout")
    if os.name == "nt":
        raise Denied("native_operation_requires_worker")
    previous_handler = signal.signal(signal.SIGALRM, expired)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.monotonic()
    signal.setitimer(signal.ITIMER_REAL, min(seconds, previous_timer[0]) if previous_timer[0] else seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0]:
            signal.setitimer(signal.ITIMER_REAL, max(0.000001, previous_timer[0] - (time.monotonic() - started)), previous_timer[1])


def gate(source, state):
    try:
        if os.name == "nt":
            return isolated_operation("_gate", [str(source), str(state)])
        with operation_timeout():
            return _gate(source, state)
    except Exception:
        return {"decision": "deny", "reason": "gate_error_or_timeout", "report_path": None}


def _gate(source, state):
    if os.name == "nt":
        from trojaino.preflight_windows import private_job
        with private_job(state) as job:
            return _gate_job(source, job)
    state = Path(state).absolute()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    job = Path(tempfile.mkdtemp(prefix="scan-", dir=state))
    return _gate_job(source, job)


def _gate_job(source, job):
    staged = job / "source"
    try:
        if source.startswith("https://"):
            try:
                stage_archive(fetch_github(source), staged)
            except OSError as exc:
                raise Denied("acquisition_error") from exc
        else:
            stage_local(source, staged)
    except (Denied, OSError, ValueError) as exc:
        result = {"decision": "deny", "reason": str(exc) if isinstance(exc, Denied) else "unsafe_source",
                  "report_path": str(job / "report.json")}
        Path(result["report_path"]).write_text(json.dumps(result) + "\n")
        return result
    files = [p for p in staged.rglob("*") if p.is_file()]
    covered = bool(files) and all(should_scan(p) and b"\0" not in p.read_bytes() for p in files)
    before_digest = tree_digest(staged)
    before_identity = scanner_identity()
    try:
        report = scan_path(staged, profile="default")
    except Exception:
        result = {"decision": "deny", "reason": "scanner_error_or_timeout",
                  "report_path": str(job / "report.json")}
        Path(result["report_path"]).write_text(json.dumps(result) + "\n")
        return result
    raw_report = report.raw_report if hasattr(report, "raw_report") else report.to_dict()
    covered = (covered and tree_digest(staged) == before_digest and scanner_identity() == before_identity
               and raw_report["complete"] is True
               and type(raw_report["files_scanned"]) is int and raw_report["files_scanned"] == len(files)
               and type(raw_report["unreadable_files"]) is int and raw_report["unreadable_files"] == 0
               and raw_report["skipped_files"] == [] and raw_report["issues"] == []
               and raw_report["schema_version"] == REPORT_SCHEMA_VERSION
               and raw_report["scanner_version"] == __version__
               and raw_report["rule_pack"] == {"id": RULE_PACK_ID, "version": RULE_PACK_VERSION}
               and raw_report["profile"] == "default" and raw_report["scan_profile"] == {"id": "default"}
               and raw_report["status"] == "complete" and type(raw_report["findings"]) is list)
    (job / "scanner.json").write_text(json.dumps(raw_report, ensure_ascii=True, indent=2) + "\n")

    result = {
        "decision": "permit" if covered and report.verdict == "NO CRITICAL RISKS FOUND" else "deny",
        "reason": "scanned" if covered else "unsupported_or_empty_coverage",
        "verdict": report.verdict,
        "profile": "default",
        "findings": [{"id": f.id, "severity": f.severity, "confidence": f.confidence,
                      "line": f.line, "file_id": hashlib.sha256(f.file.encode()).hexdigest()}
                     for f in report.findings],
        "files_scanned": report.files_scanned,
        "scanner_report_path": str(job / "scanner.json"),
        "scanner_version": __version__,
        "rule_pack": {"id": RULE_PACK_ID, "version": RULE_PACK_VERSION},
        "digest": tree_digest(staged),
        "scanner_identity": scanner_identity(),
        "staged_path": str(staged),
        "report_path": str(job / "report.json"),
    }
    Path(result["report_path"]).write_text(json.dumps(result, indent=2) + "\n")
    return result
