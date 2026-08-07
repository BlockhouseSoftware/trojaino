from __future__ import annotations

import ast
import re
from pathlib import Path

from aishield.file_utils import line_for_index
from aishield.models import CapabilityEvidence, Finding, relpath
from aishield.rules.agent_files import is_agent_file
from aishield.rules.ci import is_ci_or_deployment_path

MCP_RUNTIME_RE = re.compile(
    r"@modelcontextprotocol(?:/|\b)|\bMcpServer\b|\b(?:server\.)?(?:registerTool|register_tools|tool)\s*\(|\btools/(?:list|call)\b",
    re.I,
)
AGENT_MCP_INVOKE_RE = re.compile(
    r"(?<!not )(?<!do not )\b(?:use|invoke|call|run|execute)\b[^\n]{0,100}\bMCP\b",
    re.I,
)
SHELL_TOOL_RE = re.compile(r"\b(exec|spawn|child_process|subprocess|shell|terminal|bash|sh -c)\b", re.I)
FILESYSTEM_RE = re.compile(r"\b(readFile|writeFile|readdir|fs\.|pathlib|open\(|rm -rf|unlink)\b", re.I)
CREDENTIAL_PATH_RE = re.compile(r"(~/.ssh|~/.aws|(?<![A-Za-z0-9_])\.env\b|keychain|credentials)", re.I)
# Environment APIs are also used for harmless build/runtime flags. Only a
# clearly secret-bearing variable name establishes credential access.
ENV_SECRET_READ_RE = re.compile(
    r"(?:process\.env|import\.meta\.env|os\.environ)"
    r"(?:\.[A-Za-z_][A-Za-z0-9_]*?(?:API_KEY|TOKEN|SECRET|PRIVATE_KEY|PASSWORD)[A-Za-z0-9_]*"
    r"|\[\s*['\"][A-Za-z_][A-Za-z0-9_]*?(?:API_KEY|TOKEN|SECRET|PRIVATE_KEY|PASSWORD)[A-Za-z0-9_]*['\"]\s*\])",
    re.I,
)
CRED_PATH_RE = re.compile(
    rf"{CREDENTIAL_PATH_RE.pattern}|{ENV_SECRET_READ_RE.pattern}",
    re.I,
)
URL_RE = re.compile(r"https?://[^\s'\")]+", re.I)
GITHUB_API_RE = re.compile(r"(?:api\.github\.com|github\.com/|@octokit/|\bgithub\s*\.\s*(?:rest|request))", re.I)
DOCUMENTATION_SUFFIXES = {".md", ".mdx", ".rst"}


def _python_regex_literal_ranges(path: Path, text: str) -> list[tuple[int, int]]:
    """Return source ranges for strings passed to re.compile in Python rule code."""
    if path.suffix.lower() != ".py":
        return []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    line_offsets = [0]
    for line in text.splitlines(keepends=True):
        line_offsets.append(line_offsets[-1] + len(line))

    def offset(line: int, column: int) -> int:
        return line_offsets[line - 1] + column

    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "re"
            and node.func.attr == "compile"
        ):
            continue
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                ranges.append((
                    offset(arg.lineno, arg.col_offset),
                    offset(arg.end_lineno, arg.end_col_offset),
                ))
    return ranges


def has_mcp_runtime_signal(path: Path, text: str) -> bool:
    """Ignore scanner regex declarations while retaining actual Python MCP imports/usages."""
    pattern_ranges = _python_regex_literal_ranges(path, text)
    return any(
        not any(start <= match.start() < end for start, end in pattern_ranges)
        for match in MCP_RUNTIME_RE.finditer(text)
    )


def looks_like_mcp(path: Path, text: str) -> bool:
    if is_ci_or_deployment_path(path):
        return False
    if path.suffix.lower() in DOCUMENTATION_SUFFIXES and not is_agent_file(path):
        return False
    if is_agent_file(path):
        # An instruction file is not a runtime server. Only treat it as MCP
        # evidence when it explicitly directs an agent to invoke an MCP tool.
        return bool(AGENT_MCP_INVOKE_RE.search(text))
    lower_parts = {part.lower() for part in path.parts}
    if "mcp" in lower_parts or "mcp" in path.name.lower():
        return path.suffix.lower() != ".py" or has_mcp_runtime_signal(path, text)
    # A mention of MCP alongside a shell helper is not runtime proof. Require
    # an SDK import or protocol/tool-registration signal outside an MCP path.
    return has_mcp_runtime_signal(path, text)


def collect_capabilities(root: Path, files: list[Path], texts: dict[Path, str]) -> list[CapabilityEvidence]:
    """Summarize proven MCP runtime capabilities without affecting verdicting."""
    checks = [
        ("shell_execution", "Shell execution", "MCP_SHELL_TOOL", SHELL_TOOL_RE),
        ("filesystem_read_write", "Filesystem read/write", "MCP_FILESYSTEM_TOOL", FILESYSTEM_RE),
        ("environment_credential_access", "Environment or credential access", "MCP_CREDENTIAL_ACCESS", CRED_PATH_RE),
        ("outbound_network_access", "Outbound network access", "MCP_OUTBOUND_ENDPOINT", URL_RE),
        ("github_api_access", "GitHub/API access", "MCP_GITHUB_API_ACCESS", GITHUB_API_RE),
    ]
    capabilities: list[CapabilityEvidence] = []
    for path in files:
        text = texts.get(path, "")
        if not looks_like_mcp(path, text) or is_agent_file(path):
            continue
        rel = relpath(path, root)
        for capability_id, title, rule, regex in checks:
            match = regex.search(text)
            if match:
                capabilities.append(CapabilityEvidence(
                    capability_id, title, rel, line_for_index(text, match.start()), rule, match.group(0),
                ))
    return capabilities


def scan_mcp(root: Path, files: list[Path], texts: dict[Path, str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        text = texts.get(path, "")
        if not looks_like_mcp(path, text):
            continue
        rel = relpath(path, root)
        instruction = is_agent_file(path)
        checks = [
            ("MCP_SHELL_TOOL", "high", "MCP/tooling artifact appears to expose shell execution", SHELL_TOOL_RE, "Shell-capable tools can execute arbitrary commands with the user's local permissions.", "Require explicit user approval and least-privilege sandboxing before enabling shell tools."),
            ("MCP_FILESYSTEM_TOOL", "medium", "MCP/tooling artifact appears to access the filesystem", FILESYSTEM_RE, "Filesystem tools can read or mutate project and user files when granted to an agent.", "Limit filesystem scope to the project folder and document every file capability."),
            ("MCP_CREDENTIAL_ACCESS", "critical", "MCP/tooling artifact references credentials or environment access", CRED_PATH_RE, "Credential access through MCP/tools can expose secrets to agent-controlled workflows.", "Remove credential-path access or gate it behind explicit, narrow user approval."),
        ]
        for rule_id, severity, title, regex, why, rec in checks:
            match = regex.search(text)
            if match:
                disposition = "review"
                if not instruction and rule_id in {"MCP_SHELL_TOOL", "MCP_CREDENTIAL_ACCESS"}:
                    disposition = "actionable"
                if instruction:
                    title = title.replace(
                        "MCP/tooling artifact appears to expose",
                        "Agent instruction asks an agent to invoke",
                    )
                findings.append(Finding(
                    rule_id, severity, "medium", title, rel,
                    line_for_index(text, match.start()), match.group(0), why, rec,
                    disposition=disposition,
                ))
        urls = [m.group(0) for m in URL_RE.finditer(text)]
        if urls and any("README" not in rel for _ in urls):
            findings.append(Finding(
                id="MCP_OUTBOUND_ENDPOINT",
                severity="medium",
                confidence="medium",
                title="MCP/tooling artifact contains outbound HTTP endpoint",
                file=rel,
                line=line_for_index(text, text.find(urls[0])),
                evidence=urls[0],
                why_it_matters="Agent tools that contact external endpoints can exfiltrate data or create hidden dependencies.",
                recommendation="Verify the endpoint is disclosed in documentation and required for the tool's purpose.",
            ))
    return findings
