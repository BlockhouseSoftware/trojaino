from __future__ import annotations

import re
from pathlib import Path

from aishield.file_utils import line_for_index
from aishield.models import Finding, relpath
from aishield.rules.budget import BudgetedList, RuleBudget

KEY_VALUE_RE = re.compile(
    r"(?<![A-Z0-9_])(?P<name>[A-Z0-9_]{0,128}(API_KEY|TOKEN|SECRET|PRIVATE_KEY|PASSWORD)[A-Z0-9_]{0,128})"
    r"\s{0,32}[:=]\s{0,32}(?P<quote>['\"]?)(?P<value>[A-Za-z0-9_./+=\-]{16,4096})(?P=quote)",
    re.I,
)
CLIENT_SECRET_RE = re.compile(r"\b(VITE_|NEXT_PUBLIC_|PUBLIC_)[A-Z0-9_]*(API_KEY|TOKEN|SECRET|PRIVATE_KEY|PASSWORD)\b", re.I)
KNOWN_KEY_RE = re.compile(r"\b(sk-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})\b")
STORAGE_KEY_NAME_RE = re.compile(r"(?:^|_)(?:[A-Z0-9]+_)*(?:STORAGE|TOKEN|SESSION|CACHE|STATE|CONFIG|API)_?KEY$", re.I)
IDENTIFIER_VALUE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[._:-][A-Za-z][A-Za-z0-9]*)+$")
IDENTIFIER_LABEL_RE = re.compile(r"(?:storage|token|key|cache|session|state|config)", re.I)


def is_storage_key_identifier(name: str, value: str) -> bool:
    """Return whether a quoted value names storage/config state rather than a secret.

    Require both an identifier-shaped, namespaced value and a key-like assignment
    role. This deliberately leaves opaque strings (including token/base64 values)
    eligible for the generic hardcoded-secret rule.
    """
    return bool(
        STORAGE_KEY_NAME_RE.search(name)
        and IDENTIFIER_VALUE_RE.fullmatch(value)
        and IDENTIFIER_LABEL_RE.search(name + " " + value)
    )


def scan_secrets(root: Path, files: list[Path], texts: dict[Path, str], budget: RuleBudget | None = None) -> list[Finding]:
    findings: BudgetedList[Finding] = BudgetedList(budget)
    for path in files:
        findings.checkpoint()
        text = texts.get(path, "")
        rel = relpath(path, root)
        if path.name.startswith(".env") and path.name != ".env.example":
            findings.append(Finding(
                id="SECRET_ENV_FILE_COMMITTED",
                severity="high",
                confidence="high",
                title="Environment file is present in the scanned artifact",
                file=rel,
                line=1,
                evidence=path.name,
                why_it_matters="AI-built/downloaded projects often accidentally include real secrets in .env files.",
                recommendation="Remove real .env files from the artifact; keep only .env.example with placeholders.",
                disposition="actionable",
            ))
        for match in CLIENT_SECRET_RE.finditer(text):
            findings.append(Finding(
                id="SECRET_CLIENT_EXPOSED_KEY_NAME",
                severity="high",
                confidence="high",
                title="Client-exposed environment variable appears to hold a secret",
                file=rel,
                line=line_for_index(text, match.start()),
                evidence=match.group(0),
                why_it_matters="VITE/NEXT_PUBLIC/PUBLIC variables are normally bundled into browser-accessible code.",
                recommendation="Move secret-bearing API calls server-side and expose only non-secret public config to the browser.",
            ))
        for match in KEY_VALUE_RE.finditer(text):
            value = match.group("value")
            is_environment_assignment = path.name.startswith(".env")
            is_quoted_literal = bool(match.group("quote"))
            # A code expression such as password = generate_password() or
            # password_hmac = password_to_hmac(...) is not a hardcoded value.
            # Keep unquoted assignments for .env files, where that syntax is
            # legitimate and often sensitive, but require a quoted literal in
            # source files.
            if not is_environment_assignment and not is_quoted_literal:
                continue
            if "example" in path.name.lower() and value.lower() in {"changeme", "placeholder", "your_api_key_here"}:
                continue
            if is_storage_key_identifier(match.group("name"), value):
                continue
            findings.append(Finding(
                id="SECRET_POSSIBLE_HARDCODED_SECRET",
                severity="medium",
                confidence="medium",
                title="Possible hardcoded secret or token",
                file=rel,
                line=line_for_index(text, match.start()),
                evidence=match.group("name"),
                why_it_matters="Hardcoded secrets can be leaked when a project is shared, deployed, or scanned by other tools.",
                recommendation="Replace real values with environment lookups and rotate any exposed credentials.",
            ))
        for match in KNOWN_KEY_RE.finditer(text):
            findings.append(Finding(
                id="SECRET_KNOWN_TOKEN_PATTERN",
                severity="critical",
                confidence="high",
                title="Credential matches a known token pattern",
                file=rel,
                line=line_for_index(text, match.start()),
                evidence=match.group(0)[:8] + "…",
                why_it_matters="The artifact appears to contain a real API token pattern.",
                recommendation="Remove the token, rotate it with the provider, and rescan before sharing or deploying.",
                disposition="actionable",
            ))
    return findings
