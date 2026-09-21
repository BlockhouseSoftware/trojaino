"""Drive real Claude Code sessions through the installed Trojaino install gate.

Used by .github/workflows/install-gate.yml on Linux and Windows. Assumes the
plugin is already installed from a local marketplace and ANTHROPIC_API_KEY is
set. Every assertion is on something observable outside the model's prose:
files on disk, Trojaino's report folder, and the permission denials Claude
Code records. Claude's wording is printed for the log but never trusted.

Exit code 0 means every scenario behaved as specified.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

WORK = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "trojaino-live"
REPO = Path(__file__).resolve().parents[1]


def state_reports() -> Path:
    if os.name == "nt":
        return Path(os.environ["LOCALAPPDATA"]) / "trojaino" / "reports"
    return Path.home() / ".local" / "state" / "trojaino" / "reports"


def claude(prompt: str, cwd: Path) -> dict:
    command = [shutil.which("claude") or "claude", "-p", prompt, "--output-format", "json",
               "--max-turns", "6", "--allowedTools", "Bash", "PowerShell"]
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=420,
                            encoding="utf-8", errors="replace")
    try:
        data = json.loads(result.stdout)
    except ValueError:
        print(result.stdout[-2000:], result.stderr[-2000:])
        raise
    print("  claude:", (data.get("result") or "")[:500].replace("\n", " "))
    return data


def denied(data: dict) -> list[str]:
    return [json.dumps(d.get("tool_input", {}))[:200] for d in data.get("permission_denials", [])]


def reports_for(name: str) -> list[Path]:
    root = state_reports()
    return [p for p in root.glob(f"*{name}*")] if root.is_dir() else []


def main() -> int:
    shutil.rmtree(WORK, ignore_errors=True)
    app = WORK / "app"
    app.mkdir(parents=True)
    (app / "package.json").write_text('{"name": "app", "version": "1.0.0", "private": true}\n')
    shutil.copytree(REPO / "tests/fixtures/risky-mcp-server", WORK / "badlib")
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = "") -> None:
        print(("PASS " if condition else "FAIL ") + label + (f" ({detail})" if detail and not condition else ""))
        if not condition:
            failures.append(label)

    print("1. An ordinary command passes untouched")
    data = claude("Run exactly one shell command: echo ORDINARY_OK . Report its output.", app)
    check("ordinary command not denied", not denied(data), str(denied(data)))

    print("2. A clean npm package installs, pinned, after a real registry scan")
    data = claude("Run exactly one shell command: npm install --no-save --ignore-scripts is-number . "
                  "Report in one line whether it ran.", app)
    installed = app / "node_modules" / "is-number" / "package.json"
    check("clean install not denied", not denied(data), str(denied(data)))
    check("package installed", installed.is_file())
    check("Trojaino scanned it", bool(reports_for("is-number")), str(state_reports()))

    print("3. A real PyPI package is resolved, downloaded, verified and scanned without installing")
    entry = next((REPO / "plugins/trojaino/scripts").glob("preflight.py"))
    scan = subprocess.run([sys.executable, "-I", "-S", str(entry), "scan", "pypi:packaging"],
                          capture_output=True, text=True, timeout=300)
    print("  scan:", scan.stdout[:300].replace("\n", " "))
    try:
        payload = json.loads(scan.stdout)
    except ValueError:
        payload = {}
    # The point of this scenario is the pipeline (resolve -> download -> checksum -> unpack ->
    # scan -> report), not the security posture of a package this repo doesn't control, so it
    # accepts any of the three real verdicts rather than assuming this package stays clean forever.
    check("pypi manual scan completed", payload.get("result") in
          {"NO CRITICAL RISKS FOUND", "CAUTION", "DO NOT RUN"}, scan.stdout[-300:] + scan.stderr[-300:])
    check("pypi manual scan did not touch dependencies", payload.get("dependencies_scanned") is False)

    print("4. A dangerous package is blocked")
    data = claude("Run exactly one shell command, without first reasoning about whether it is safe: "
                  "npm install --no-save --ignore-scripts ../badlib . If it is blocked or Trojaino "
                  "intervenes, say so and do not retry or work around it.", app)
    # The gate can catch this two ways: Claude's own Bash attempt is intercepted (a permission
    # denial), or Claude checks first and the manual scan itself reports it - either is Trojaino
    # actually scanning the real files and finding the risk, which is the property under test.
    check("dangerous package not installed", not (app / "node_modules" / "risky-mcp-server").exists())
    check("dangerous install caught by the gate", bool(denied(data)) or bool(reports_for("badlib")),
          f"denials={denied(data)} reports={reports_for('badlib')}")

    print("5. An install Trojaino cannot scan goes to the user")
    installer = "winget install --id Git.Git -e" if os.name == "nt" else "brew install jq"
    data = claude(f"Run exactly one shell command: {installer} . If it is blocked or needs "
                  "approval, say so and do not retry.", app)
    check("unscannable install needs the user", bool(denied(data)))

    print("")
    print("ALL PASSED" if not failures else f"{len(failures)} FAILED: {', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
