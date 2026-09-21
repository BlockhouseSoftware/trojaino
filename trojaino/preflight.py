"""Hook entry point and scanner isolation for the Claude Code install gate.

The policy lives in trojaino.gate. This module only reads the hook event,
runs the scanner in a separate trusted process, and prints the answer.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

from trojaino import __version__
from trojaino.contract import RULE_PACK_ID, RULE_PACK_VERSION

SCAN_TIMEOUT = 20.0
HOOK_WATCHDOG_SECONDS = 110


class Denied(Exception):
    pass


def trusted_environment():
    """A minimal environment for the scanner worker: no PYTHON* variables, no PATH tricks."""
    if os.name == "nt":
        root = os.environ.get("SystemRoot") or r"C:\Windows"
        return {"SystemRoot": root, "PATH": str(Path(root) / "System32"), "LANG": "C.UTF-8"}
    return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


def scan_path(target, profile="package"):
    """Run the scanner in an isolated process so a hostile file cannot hang the hook."""
    worker = getattr(sys.modules["trojaino"], "_sealed_worker", None)
    if worker is not None:
        report = worker("scan_path", [str(target), profile], timeout=SCAN_TIMEOUT)
    else:
        trusted = str(Path(__file__).resolve().parent.parent)
        code = ("import sys,json; sys.path.insert(0,sys.argv[1]); "
                "from trojaino.scanner import scan_path,ScanLimits; "
                "r=scan_path(sys.argv[2],profile=sys.argv[3],limits=ScanLimits(max_elapsed_seconds=15)); "
                "print(json.dumps(r.to_dict()))")
        with tempfile.TemporaryFile() as output:
            subprocess.run([sys.executable, "-I", "-S", "-c", code, trusted, str(target), profile],
                           cwd=trusted, stdin=subprocess.DEVNULL, stdout=output,
                           stderr=subprocess.DEVNULL, timeout=SCAN_TIMEOUT, check=True,
                           env=trusted_environment())
            output.seek(0)
            data = output.read(5_000_001)
        if len(data) > 5_000_000:
            raise Denied("scanner_output_limit")
        report = json.loads(data)
    report["raw_report"] = dict(report)
    return SimpleNamespace(**report)


def scanner_identity():
    """Changes whenever the scanner or its rules change, so cached verdicts expire."""
    sealed_identity = getattr(sys.modules["trojaino"], "_sealed_identity", None)
    if sealed_identity is not None:
        return sealed_identity
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    digest.update(json.dumps([__version__, RULE_PACK_ID, RULE_PACK_VERSION]).encode())
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0" + path.read_bytes() + b"\0")
    return digest.hexdigest()


@contextmanager
def watchdog(seconds=HOOK_WATCHDOG_SECONDS):
    """POSIX backstop below the host's hook timeout. Windows relies on per-step limits."""
    if os.name == "nt" or not hasattr(signal, "SIGALRM"):
        yield
        return

    def expired(signum, frame):
        raise Denied("gate_timeout")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def hook_input():
    data = sys.stdin.buffer.read(1_000_001)
    if len(data) > 1_000_000:
        raise Denied("invalid_input")
    event = json.loads(data)
    if not isinstance(event, dict):
        raise Denied("invalid_input")
    return event


def run_hook():
    from trojaino.gate import handle
    try:
        event = hook_input()
    except Exception:
        return None
    try:
        with watchdog():
            return handle(event)
    except Exception:
        if event.get("hook_event_name") == "PreToolUse":
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "ask",
                    "permissionDecisionReason": "Trojaino could not finish checking this command in time. "
                                                "Decide whether to allow it."}}
        return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["hook"]:
        result = run_hook()
        if result:
            print(json.dumps(result, ensure_ascii=True))
        return 0
    parser = argparse.ArgumentParser(description="Trojaino install gate helper")
    sub = parser.add_subparsers(dest="action", required=True)
    scan = sub.add_parser("scan", help="scan a package, repository or folder without installing it")
    scan.add_argument("source", help="npm:NAME[@VERSION], pypi:NAME[==VERSION], a GitHub URL, or a path")
    args = parser.parse_args(argv)
    from trojaino.gate import scan_source
    with watchdog():
        result = scan_source(args.source, os.getcwd())
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result.get("result") == "NO CRITICAL RISKS FOUND" else 2
