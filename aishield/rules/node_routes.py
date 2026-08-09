from __future__ import annotations

import re
from pathlib import Path

from aishield.file_utils import line_for_index
from aishield.models import Finding, relpath
from aishield.rules.budget import BudgetedList, RuleBudget

ROUTE_RE = re.compile(r"\b(app|router)\.(delete|post|put|patch|get)\s*\(\s*['\"]([^'\"]+)['\"]", re.I)
AUTH_RE = re.compile(r"\b(requireAuth|isAuthenticated|authMiddleware|verifySession|requireAdmin|ensureAuth|authorize|protect)\b")
DESTRUCTIVE_RE = re.compile(r"(delete|destroy|remove|reset|truncate|wipe|admin|drop)", re.I)
BAD_CORS_RE = re.compile(
    r"\bcors\s*\(\s*\)"
    r"|\bcors\s*\([^)]*origin\s*:\s*(?:['\"]\*['\"]|true)"
    r"|Access-Control-Allow-Origin['\"]?\s*,\s*['\"]\*['\"]",
    re.I | re.S,
)
LOCAL_STORAGE_AUTH_RE = re.compile(
    r"\blocalStorage\s*\.\s*(?:setItem|getItem)\s*\(\s*['\"][^'\"]*(?:token|jwt|session|auth|secret)[^'\"]*['\"]"
    r"|\blocalStorage\s*\[[^\]]*['\"][^'\"]*(?:token|jwt|session|auth|secret)[^'\"]*['\"][^\]]*\]",
    re.I,
)
SAFE_TEMP_UPLOAD_CLEANUP_RE = re.compile(
    r"\b(?:fs\s*\.\s*)?rm\s*\(\s*originalPath\s*,\s*\{\s*force\s*:\s*true\s*\}\s*\)",
    re.I,
)
TEST_RUNNER_SPAWN_RE = re.compile(
    r"\bspawn\s*\(\s*['\"](?:node|nodejs|npm|yarn|pnpm)['\"]\s*,\s*\[[^\]]*"
    r"(?:--test|jest|vitest|mocha|ava|tap|tests?)",
    re.I | re.S,
)
DANGEROUS_OPS = [
    ("NODE_SHELL_EXEC", "high", "Node code appears to execute shell commands", re.compile(r"\b(exec|spawn|execFile)\s*\(|child_process", re.I), "Shell execution from app code is high risk, especially if user input can reach it.", "Review data flow into shell calls and replace shell execution with safe library APIs when possible."),
    ("NODE_EVAL", "high", "Node code uses eval-like execution", re.compile(r"\beval\s*\(|new Function\s*\(", re.I), "Eval-like execution can turn user-controlled strings into code execution.", "Remove eval-like behavior or strictly constrain and validate inputs."),
    ("NODE_FILE_DELETE", "medium", "Node code deletes files or directories", re.compile(r"\b(rmSync|unlinkSync|rmdirSync|rm\s*\(|unlink\s*\()", re.I), "Generated apps can accidentally expose destructive file operations through routes or jobs.", "Ensure deletion paths are fixed, scoped, authenticated, and not built from raw user input."),
]


def is_node_file(path: Path) -> bool:
    return path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def scan_node_routes(root: Path, files: list[Path], texts: dict[Path, str], budget: RuleBudget | None = None) -> list[Finding]:
    findings: BudgetedList[Finding] = BudgetedList(budget)
    for path in files:
        findings.checkpoint()
        if not is_node_file(path):
            continue
        text = texts.get(path, "")
        rel = relpath(path, root)
        for match in ROUTE_RE.finditer(text):
            method = match.group(2).lower()
            route = match.group(3)
            snippet_start = max(0, match.start() - 500)
            snippet_end = min(len(text), match.end() + 500)
            local = text[snippet_start:snippet_end]
            if (method in {"delete", "post", "put", "patch"} or DESTRUCTIVE_RE.search(route)) and DESTRUCTIVE_RE.search(route) and not AUTH_RE.search(local):
                findings.append(Finding(
                    id="NODE_UNAUTH_DESTRUCTIVE_ROUTE",
                    severity="high",
                    confidence="medium",
                    title="Potential unauthenticated destructive route",
                    file=rel,
                    line=line_for_index(text, match.start()),
                    evidence=f"{method.upper()} {route}",
                    why_it_matters="AI-generated apps commonly scaffold destructive endpoints without auth or role checks.",
                    recommendation="Require authenticated admin/owner middleware before this route handler mutates data.",
                ))
        cors_match = BAD_CORS_RE.search(text)
        if cors_match:
            findings.append(Finding(
                id="NODE_PERMISSIVE_CORS",
                severity="high",
                confidence="medium",
                title="Node app appears to allow broad cross-origin access",
                file=rel,
                line=line_for_index(text, cors_match.start()),
                evidence=cors_match.group(0).strip(),
                why_it_matters="A wildcard or reflection-style CORS policy can expose APIs to arbitrary websites, especially when combined with browser credentials or token storage.",
                recommendation="Restrict CORS origins to the exact trusted app domains and avoid reflecting arbitrary request origins.",
                disposition="actionable",
            ))
        local_storage_match = LOCAL_STORAGE_AUTH_RE.search(text)
        if local_storage_match:
            findings.append(Finding(
                id="NODE_LOCAL_STORAGE_AUTH_TOKEN",
                severity="high",
                confidence="medium",
                title="Browser code appears to store auth tokens in localStorage",
                file=rel,
                line=line_for_index(text, local_storage_match.start()),
                evidence=local_storage_match.group(0).strip(),
                why_it_matters="Tokens stored in localStorage are exposed to any injected script, making XSS or poisoned dependencies more likely to become account takeover.",
                recommendation="Prefer HttpOnly, Secure, SameSite cookies or another storage pattern that keeps session secrets out of JavaScript-readable storage.",
                disposition="actionable",
            ))
        for rule_id, severity, title, regex, why, rec in DANGEROUS_OPS:
            safe_cleanup_ranges = [(cleanup.start(), cleanup.end()) for cleanup in SAFE_TEMP_UPLOAD_CLEANUP_RE.finditer(text)]
            match = next(
                (
                    candidate for candidate in regex.finditer(text)
                    if rule_id != "NODE_FILE_DELETE"
                    or not any(start <= candidate.start() < end for start, end in safe_cleanup_ranges)
                ),
                None,
            )
            if not match:
                continue
            test_runner_match = TEST_RUNNER_SPAWN_RE.search(text) if rule_id == "NODE_SHELL_EXEC" else None
            if test_runner_match:
                findings.append(Finding(
                    rule_id,
                    severity,
                    "high",
                    "Node test runner spawns a local test process",
                    rel,
                    line_for_index(text, test_runner_match.start()),
                    test_runner_match.group(0).strip(),
                    "This invokes a fixed local test command rather than a dynamically constructed production shell command.",
                    "Keep the executable and test arguments fixed; review any future change that incorporates external input.",
                    disposition="likely_test_or_example",
                ))
                continue
            findings.append(Finding(rule_id, severity, "medium", title, rel, line_for_index(text, match.start()), match.group(0), why, rec))
    return findings
