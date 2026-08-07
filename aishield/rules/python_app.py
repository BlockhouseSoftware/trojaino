from __future__ import annotations

import ast
import re
from pathlib import Path

from aishield.file_utils import line_for_index
from aishield.models import Finding, relpath

ROUTE_DECORATOR_RE = re.compile(
    r"@\s*(?:app|router|blueprint|bp)\s*\.\s*(?:route|get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.I,
)
ROUTE_METHODS_RE = re.compile(r"methods\s*=\s*\[[^\]]*['\"](POST|PUT|PATCH|DELETE)['\"]", re.I)
FASTAPI_ROUTE_RE = re.compile(r"@\s*(?:app|router)\s*\.\s*(get|post|put|patch|delete)\s*\(", re.I)
AUTH_RE = re.compile(
    r"\b(login_required|jwt_required|permission_required|require_auth|require_admin|auth_required|"
    r"Depends\s*\([^)]*(?:auth|get_current_user|require_admin|oauth|token)|"
    r"current_user|is_authenticated|verify_token|authenticate|authorize)\b",
    re.I,
)
DESTRUCTIVE_RE = re.compile(r"(admin|delete|destroy|remove|reset|truncate|wipe|drop)", re.I)
DEBUG_RE = re.compile(r"\bdebug\s*=\s*True\b|\bDEBUG\s*=\s*True\b")
PERMISSIVE_CORS_RE = re.compile(
    r"allow_origins\s*=\s*\[\s*['\"]\*['\"]\s*\]"
    r"|CORS\s*\(\s*app\s*\)"
    r"|origins\s*=\s*['\"]\*['\"]",
    re.I | re.S,
)
REQUEST_SOURCE_RE = re.compile(
    r"\brequest\s*\.\s*(?:args|form|json|files|values|get_json)\b"
    r"|\binput\s*\(",
    re.I,
)
SINK_RE = re.compile(
    r"\b(?:subprocess\s*\.\s*(?:run|call|Popen|check_output|check_call)|os\s*\.\s*system|"
    r"open|Path|send_file|requests\s*\.\s*(?:get|post|put|patch|delete))\s*\(",
    re.I,
)


def is_python_file(path: Path) -> bool:
    return path.suffix.lower() == ".py"


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _keyword_bool(call: ast.Call, name: str, value: bool) -> bool:
    for keyword in call.keywords:
        if keyword.arg == name and isinstance(keyword.value, ast.Constant) and keyword.value.value is value:
            return True
    return False


def _yaml_load_has_safe_loader(call: ast.Call) -> bool:
    for keyword in call.keywords:
        if keyword.arg in {"Loader", "loader"}:
            loader_name = _call_name(keyword.value)
            if "SafeLoader" in loader_name or "safe" in loader_name.lower():
                return True
    return False


def _evidence_for_call(text: str, node: ast.AST, fallback: str) -> str:
    try:
        segment = ast.get_source_segment(text, node)
    except Exception:
        segment = None
    return (segment or fallback).strip()


def _line(node: ast.AST) -> int | None:
    return getattr(node, "lineno", None)


def _append_call_finding(findings: list[Finding], *, rule_id: str, severity: str, confidence: str, title: str, rel: str, node: ast.AST, text: str, why: str, rec: str, disposition: str = "review") -> None:
    findings.append(Finding(
        id=rule_id,
        severity=severity,
        confidence=confidence,
        title=title,
        file=rel,
        line=_line(node),
        evidence=_evidence_for_call(text, node, title),
        why_it_matters=why,
        recommendation=rec,
        disposition=disposition,
    ))


def scan_python_app(root: Path, files: list[Path], texts: dict[Path, str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if not is_python_file(path):
            continue
        text = texts.get(path, "")
        rel = relpath(path, root)
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            findings.append(Finding(
                id="PY_SYNTAX_ERROR",
                severity="medium",
                confidence="high",
                title="Python file could not be parsed",
                file=rel,
                line=exc.lineno,
                evidence=(exc.text or "syntax error").strip(),
                why_it_matters="Unparseable Python can hide behavior from AST-based checks and may indicate broken generated code.",
                recommendation="Fix the syntax error and rescan so Python-specific checks can inspect the file.",
            ))
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node.func)
            lower_name = name.lower()
            if lower_name in {"eval", "exec"}:
                _append_call_finding(
                    findings,
                    rule_id="PY_EVAL_EXEC",
                    severity="high",
                    confidence="high",
                    title="Python code uses eval/exec",
                    rel=rel,
                    node=node,
                    text=text,
                    why="eval/exec can turn strings into code execution, especially dangerous in generated apps or admin tools.",
                    rec="Remove eval/exec or replace it with a constrained parser or explicit command map.",
                    disposition="actionable",
                )
            elif lower_name == "os.system":
                _append_call_finding(
                    findings,
                    rule_id="PY_OS_SYSTEM",
                    severity="high",
                    confidence="high",
                    title="Python code executes a shell command with os.system",
                    rel=rel,
                    node=node,
                    text=text,
                    why="os.system invokes a shell and is easy to misuse with user-controlled input.",
                    rec="Use safe library APIs or subprocess with fixed argument lists and no shell.",
                    disposition="actionable",
                )
            elif lower_name in {"subprocess.run", "subprocess.call", "subprocess.popen", "subprocess.check_output", "subprocess.check_call"} and _keyword_bool(node, "shell", True):
                _append_call_finding(
                    findings,
                    rule_id="PY_SUBPROCESS_SHELL_TRUE",
                    severity="high",
                    confidence="high",
                    title="Python subprocess call enables shell=True",
                    rel=rel,
                    node=node,
                    text=text,
                    why="shell=True routes command strings through a shell, which can become command injection if any external input reaches it.",
                    rec="Pass an argument list with shell=False and validate any user-controlled values before execution.",
                    disposition="actionable",
                )
            elif lower_name in {"pickle.load", "pickle.loads"}:
                _append_call_finding(
                    findings,
                    rule_id="PY_PICKLE_DESERIALIZATION",
                    severity="high",
                    confidence="medium",
                    title="Python code deserializes pickle data",
                    rel=rel,
                    node=node,
                    text=text,
                    why="Pickle can execute code while loading data and is unsafe for untrusted input.",
                    rec="Use JSON or another safe data format for untrusted data; only load pickle from fully trusted sources.",
                    disposition="actionable",
                )
            elif lower_name == "yaml.load" and not _yaml_load_has_safe_loader(node):
                _append_call_finding(
                    findings,
                    rule_id="PY_YAML_UNSAFE_LOAD",
                    severity="high",
                    confidence="medium",
                    title="Python code calls yaml.load without an explicit SafeLoader",
                    rel=rel,
                    node=node,
                    text=text,
                    why="Unsafe YAML loaders can instantiate objects or execute surprising behavior when parsing untrusted YAML.",
                    rec="Use yaml.safe_load(...) or yaml.load(..., Loader=yaml.SafeLoader).",
                    disposition="actionable",
                )
            elif lower_name.endswith(".run") and _keyword_bool(node, "debug", True):
                _append_call_finding(
                    findings,
                    rule_id="PY_DEBUG_MODE_ENABLED",
                    severity="high",
                    confidence="medium",
                    title="Python web app appears to enable debug mode",
                    rel=rel,
                    node=node,
                    text=text,
                    why="Debug mode can expose interactive debuggers, stack traces, and sensitive configuration in deployed Python apps.",
                    rec="Disable debug mode outside local development and load environment-specific settings explicitly.",
                    disposition="actionable",
                )

        debug_match = DEBUG_RE.search(text)
        if debug_match:
            findings.append(Finding(
                id="PY_DEBUG_MODE_ENABLED",
                severity="high",
                confidence="medium",
                title="Python web app appears to enable debug mode",
                file=rel,
                line=line_for_index(text, debug_match.start()),
                evidence=debug_match.group(0).strip(),
                why_it_matters="Debug mode can expose stack traces, config, or interactive debuggers if deployed accidentally.",
                recommendation="Disable debug mode in committed defaults and production configs.",
                disposition="actionable",
            ))

        cors_match = PERMISSIVE_CORS_RE.search(text)
        if cors_match:
            findings.append(Finding(
                id="PY_PERMISSIVE_CORS",
                severity="high",
                confidence="medium",
                title="Python app appears to allow broad cross-origin access",
                file=rel,
                line=line_for_index(text, cors_match.start()),
                evidence=cors_match.group(0).strip(),
                why_it_matters="Wildcard CORS can expose APIs to arbitrary websites, especially when paired with cookies, bearer tokens, or browser-based tools.",
                recommendation="Restrict allowed origins to exact trusted domains and avoid wildcard defaults.",
                disposition="actionable",
            ))

        for match in ROUTE_DECORATOR_RE.finditer(text):
            route = match.group(1)
            local = text[max(0, match.start() - 350):min(len(text), match.end() + 800)]
            method_is_mutating = bool(ROUTE_METHODS_RE.search(local) or FASTAPI_ROUTE_RE.search(local) and FASTAPI_ROUTE_RE.search(local).group(1).lower() in {"post", "put", "patch", "delete"})
            if DESTRUCTIVE_RE.search(route) and (method_is_mutating or DESTRUCTIVE_RE.search(route)) and not AUTH_RE.search(local):
                findings.append(Finding(
                    id="PY_UNAUTH_DESTRUCTIVE_ROUTE",
                    severity="high",
                    confidence="medium",
                    title="Potential unauthenticated destructive Python route",
                    file=rel,
                    line=line_for_index(text, match.start()),
                    evidence=match.group(0).strip(),
                    why_it_matters="AI-generated Flask/FastAPI apps often scaffold admin or destructive routes before auth and role checks are added.",
                    recommendation="Require authentication and admin/owner authorization before destructive route handlers mutate data or files.",
                    disposition="actionable",
                ))

        if REQUEST_SOURCE_RE.search(text) and SINK_RE.search(text):
            source_match = REQUEST_SOURCE_RE.search(text)
            sink_match = SINK_RE.search(text)
            if source_match and sink_match:
                findings.append(Finding(
                    id="PY_USER_INPUT_TO_SENSITIVE_SINK",
                    severity="medium",
                    confidence="low",
                    title="Python code combines user input sources with sensitive sinks",
                    file=rel,
                    line=line_for_index(text, min(source_match.start(), sink_match.start())),
                    evidence=f"source: {source_match.group(0).strip()} / sink: {sink_match.group(0).strip()}",
                    why_it_matters="User-controlled request data near shell, file, path, send_file, or outbound request calls can become command injection, path traversal, data exposure, or SSRF.",
                    recommendation="Trace the data flow manually; validate/normalize user input and keep it out of shell commands, arbitrary paths, and server-side URL fetches.",
                ))
    return findings
