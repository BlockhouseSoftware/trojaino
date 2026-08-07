from __future__ import annotations

import re
from pathlib import Path

from aishield.file_utils import line_for_index
from aishield.models import Finding, relpath

AGENT_FILE_NAMES = {"AGENTS.md", "CLAUDE.md", ".windsurfrules"}
AGENT_PATH_PARTS = {".cursor"}
ZERO_WIDTH_RE = re.compile("[\u200b\u200c\u200d\ufeff]")
PATTERNS = [
    ("AGENT_IGNORE_SAFETY", "high", "Agent instruction attempts to override safety rules", re.compile(r"ignore (all )?((previous|prior|system|safety|security|local)\s+){1,3}(instructions|rules|warnings)", re.I), "Instruction override text can steer future coding agents away from the user's intended safety policy.", "Remove override language and keep project instructions scoped to legitimate build/test behavior."),
    ("AGENT_HIDE_BEHAVIOR", "high", "Agent instruction tells the agent to hide behavior from the user", re.compile(r"(do not|don't|never) (tell|inform|mention|warn) (the )?user|silently (run|install|execute)", re.I), "Instructions to hide behavior are a strong signal of malicious or unsafe agent guidance.", "Remove secrecy language; all install, network, and file operations should be visible to the user."),
    ("AGENT_SECRET_EXFIL", "critical", "Agent instruction references secret or credential exfiltration", re.compile(r"(exfiltrate|send|upload|post).*(\.env|api key|token|secret|~/.ssh|\.aws|credentials)", re.I | re.S), "Agent-readable markdown can instruct future agents to leak secrets using their own tool access.", "Do not load this file into an agent until the instruction is removed and the source is trusted."),
    ("AGENT_CREDENTIAL_PATH", "high", "Agent instruction references sensitive local credential paths", re.compile(r"(~/.ssh|~/.aws|\.env|keychain|credentials)", re.I), "Agent instructions that mention sensitive local paths can expand the future agent's file-access scope.", "Require a specific, user-approved reason before any agent instruction touches credential paths."),
    ("AGENT_TRUST_REMOTE_DOCS", "medium", "Agent instruction tells agents to trust remote content", re.compile(r"trust .*remote|always follow .*web|treat .*docs .*authoritative", re.I), "Remote content can contain prompt injection and should not automatically override local policy.", "Tell agents to treat remote content as untrusted data unless the user approves it."),
]


def is_agent_file(path: Path) -> bool:
    if path.name in AGENT_FILE_NAMES:
        return True
    if any(part in AGENT_PATH_PARTS for part in path.parts) and path.suffix.lower() in {".md", ".txt"}:
        return True
    return path.name.lower() in {"rules", "prompts.md", "prompt.md"}


def scan_agent_files(root: Path, files: list[Path], texts: dict[Path, str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if not is_agent_file(path):
            continue
        text = texts.get(path, "")
        rel = relpath(path, root)
        for match in ZERO_WIDTH_RE.finditer(text):
            findings.append(Finding(
                id="AGENT_HIDDEN_UNICODE",
                severity="medium",
                confidence="high",
                title="Hidden zero-width unicode appears in agent instruction file",
                file=rel,
                line=line_for_index(text, match.start()),
                evidence="zero-width unicode character",
                why_it_matters="Invisible characters can hide instructions or make manual review unreliable.",
                recommendation="Remove hidden unicode and re-review the visible instruction text.",
            ))
        for rule_id, severity, title, regex, why, rec in PATTERNS:
            match = regex.search(text)
            if not match:
                continue
            evidence = " ".join(match.group(0).split())[:220]
            disposition = "actionable" if rule_id in {"AGENT_IGNORE_SAFETY", "AGENT_HIDE_BEHAVIOR", "AGENT_SECRET_EXFIL"} else "review"
            findings.append(Finding(rule_id, severity, "high", title, rel, line_for_index(text, match.start()), evidence, why, rec, disposition=disposition))
    return findings
