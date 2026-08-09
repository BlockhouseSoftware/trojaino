from __future__ import annotations

import json
import re
from pathlib import Path

from aishield.file_utils import line_number
from aishield.models import Finding, relpath
from aishield.rules.budget import BudgetedList, RuleBudget

LIFECYCLE_SCRIPTS = {"preinstall", "install", "postinstall", "prepare"}
REMOTE_EXEC_RE = re.compile(r"\b(curl|wget)\b[^\n;&|]*(https?://[^\s'\"]+)[^\n]*(\|\s*(bash|sh)|-O\s*-)", re.I)
SHELL_EVAL_RE = re.compile(r"\b(node|python|perl|ruby)\s+-e\b|\beval\s*\(|\bbase64\s+-d\b", re.I)
CREDENTIAL_PATH_RE = re.compile(r"(~/(\.ssh|\.aws|\.config)|\$HOME/(\.ssh|\.aws|\.config)|/etc/passwd|\.env)", re.I)


def scan_package_json(root: Path, files: list[Path], texts: dict[Path, str], budget: RuleBudget | None = None) -> list[Finding]:
    findings: BudgetedList[Finding] = BudgetedList(budget)
    for path in files:
        findings.checkpoint()
        if path.name != "package.json":
            continue
        text = texts.get(path, "")
        parse_text = text[1:] if text.startswith("\ufeff") else text
        try:
            package = json.loads(parse_text)
        except json.JSONDecodeError:
            findings.append(Finding(
                id="PKG_JSON_PARSE_ERROR",
                severity="medium",
                confidence="high",
                title="package.json could not be parsed",
                file=relpath(path, root),
                line=None,
                evidence="Invalid JSON in package manifest",
                why_it_matters="A malformed package manifest can hide install behavior from normal tooling.",
                recommendation="Fix package.json before installing or scanning further.",
            ))
            continue
        if not isinstance(package, dict):
            findings.append(Finding(
                id="PKG_JSON_INVALID_TYPE",
                severity="medium",
                confidence="high",
                title="package.json root must be an object",
                file=relpath(path, root),
                line=None,
                evidence=f"JSON root type: {type(package).__name__}",
                why_it_matters="Package tooling expects a JSON object; another root type can bypass manifest checks.",
                recommendation="Replace the manifest root with a valid package object before installing.",
            ))
            continue
        scripts = package.get("scripts", {})
        if not isinstance(scripts, dict):
            findings.append(Finding(
                id="PKG_JSON_INVALID_TYPE",
                severity="medium",
                confidence="high",
                title="package.json scripts must be an object",
                file=relpath(path, root),
                line=line_number(text, '"scripts"'),
                evidence=f"scripts type: {type(scripts).__name__}",
                why_it_matters="A malformed scripts field cannot be reliably checked for install hooks.",
                recommendation="Replace scripts with an object of script names and string commands.",
            ))
            continue
        for name, command in scripts.items():
            findings.checkpoint()
            if not isinstance(command, str):
                continue
            script_evidence = f'"{name}": "{command}"'
            line = line_number(text, f'"{name}"')
            if name in LIFECYCLE_SCRIPTS and REMOTE_EXEC_RE.search(command):
                findings.append(Finding(
                    id="PKG_REMOTE_LIFECYCLE_EXEC",
                    severity="critical",
                    confidence="high",
                    title="Remote shell script runs during package install",
                    file=relpath(path, root),
                    line=line,
                    evidence=script_evidence,
                    why_it_matters="Package lifecycle scripts execute during install, before the user has reviewed or run the app.",
                    recommendation="Remove the lifecycle hook; vendor the script or document a manual install step explicitly.",
                    disposition="actionable",
                ))
            elif name in LIFECYCLE_SCRIPTS:
                findings.append(Finding(
                    id="PKG_LIFECYCLE_SCRIPT",
                    severity="medium",
                    confidence="high",
                    title="Package lifecycle script executes during install",
                    file=relpath(path, root),
                    line=line,
                    evidence=script_evidence,
                    why_it_matters="Lifecycle scripts run automatically on install and can mutate the machine before app review.",
                    recommendation="Review the script carefully; remove it if it is not required for local build setup.",
                ))
            if SHELL_EVAL_RE.search(command):
                findings.append(Finding(
                    id="PKG_OBFUSCATED_SCRIPT_BEHAVIOR",
                    severity="high",
                    confidence="medium",
                    title="Package script uses eval-like or inline interpreter behavior",
                    file=relpath(path, root),
                    line=line,
                    evidence=script_evidence,
                    why_it_matters="Inline interpreter/eval patterns make install or build behavior harder to inspect and can hide malicious logic.",
                    recommendation="Replace inline/eval script behavior with a checked-in, reviewable script file.",
                ))
            if CREDENTIAL_PATH_RE.search(command):
                findings.append(Finding(
                    id="PKG_SCRIPT_TOUCHES_CREDENTIAL_PATHS",
                    severity="high",
                    confidence="high",
                    title="Package script references credential or home-directory paths",
                    file=relpath(path, root),
                    line=line,
                    evidence=script_evidence,
                    why_it_matters="Install/build scripts should not inspect SSH, cloud, config, or environment files without explicit user intent.",
                    recommendation="Remove credential-path access or require an explicit documented command after review.",
                ))
    return findings
