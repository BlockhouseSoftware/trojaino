"""Stable identities for deterministic Trojaino finding rules.

Rule IDs are public machine-contract identifiers. Keep definitions append-only:
retire an ID instead of reusing it, and allocate a new ID when a rule's
security meaning changes materially.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable

from trojaino.contract import RULE_PACK_ID, RULE_PACK_VERSION


@dataclass(frozen=True)
class RuleDefinition:
    """Immutable public identity for one deterministic finding rule."""

    id: str
    family: str
    status: str = "active"


def _definitions() -> tuple[RuleDefinition, ...]:
    return (
        RuleDefinition("PKG_JSON_PARSE_ERROR", "package_manifest"),
        RuleDefinition("PKG_JSON_INVALID_TYPE", "package_manifest"),
        RuleDefinition("PKG_REMOTE_LIFECYCLE_EXEC", "package_manifest"),
        RuleDefinition("PKG_LIFECYCLE_SCRIPT", "package_manifest"),
        RuleDefinition("PKG_OBFUSCATED_SCRIPT_BEHAVIOR", "package_manifest"),
        RuleDefinition("PKG_SCRIPT_TOUCHES_CREDENTIAL_PATHS", "package_manifest"),
        RuleDefinition("CI_SECRET_TRANSMISSION", "ci_or_deployment"),
        RuleDefinition("CI_SECRET_REFERENCE", "ci_or_deployment"),
        RuleDefinition("SECRET_ENV_FILE_COMMITTED", "secrets"),
        RuleDefinition("SECRET_CLIENT_EXPOSED_KEY_NAME", "secrets"),
        RuleDefinition("SECRET_POSSIBLE_HARDCODED_SECRET", "secrets"),
        RuleDefinition("SECRET_KNOWN_TOKEN_PATTERN", "secrets"),
        RuleDefinition("DOCKER_PRIVILEGED_CONTAINER", "docker"),
        RuleDefinition("DOCKER_SOCKET_MOUNT", "docker"),
        RuleDefinition("DOCKER_HOME_MOUNT", "docker"),
        RuleDefinition("DOCKER_RUNS_AS_ROOT", "docker"),
        RuleDefinition("DOCKER_ADMIN_PORT_EXPOSED", "docker"),
        RuleDefinition("AGENT_HIDDEN_UNICODE", "agent_instruction"),
        RuleDefinition("AGENT_IGNORE_SAFETY", "agent_instruction"),
        RuleDefinition("AGENT_HIDE_BEHAVIOR", "agent_instruction"),
        RuleDefinition("AGENT_SECRET_EXFIL", "agent_instruction"),
        RuleDefinition("AGENT_CREDENTIAL_PATH", "agent_instruction"),
        RuleDefinition("AGENT_TRUST_REMOTE_DOCS", "agent_instruction"),
        RuleDefinition("MCP_SHELL_TOOL", "mcp_or_tooling"),
        RuleDefinition("MCP_FILESYSTEM_TOOL", "mcp_or_tooling"),
        RuleDefinition("MCP_CREDENTIAL_ACCESS", "mcp_or_tooling"),
        RuleDefinition("MCP_OUTBOUND_ENDPOINT", "mcp_or_tooling"),
        RuleDefinition("NODE_UNAUTH_DESTRUCTIVE_ROUTE", "node"),
        RuleDefinition("NODE_PERMISSIVE_CORS", "node"),
        RuleDefinition("NODE_LOCAL_STORAGE_AUTH_TOKEN", "node"),
        RuleDefinition("NODE_SHELL_EXEC", "node"),
        RuleDefinition("NODE_EVAL", "node"),
        RuleDefinition("NODE_FILE_DELETE", "node"),
        RuleDefinition("PY_SYNTAX_ERROR", "python"),
        RuleDefinition("PY_EVAL_EXEC", "python"),
        RuleDefinition("PY_OS_SYSTEM", "python"),
        RuleDefinition("PY_SUBPROCESS_SHELL_TRUE", "python"),
        RuleDefinition("PY_PICKLE_DESERIALIZATION", "python"),
        RuleDefinition("PY_YAML_UNSAFE_LOAD", "python"),
        RuleDefinition("PY_DEBUG_MODE_ENABLED", "python"),
        RuleDefinition("PY_PERMISSIVE_CORS", "python"),
        RuleDefinition("PY_UNAUTH_DESTRUCTIVE_ROUTE", "python"),
        RuleDefinition("PY_USER_INPUT_TO_SENSITIVE_SINK", "python"),
        RuleDefinition("PYPROJECT_TOML_PARSE_ERROR", "python_packaging"),
        RuleDefinition("PYPROJECT_DIRECT_BUILD_REQUIREMENT", "python_packaging"),
        RuleDefinition("PYPROJECT_DIRECT_RUNTIME_DEPENDENCY", "python_packaging"),
        RuleDefinition("PYPROJECT_EXTRA_PACKAGE_INDEX", "python_packaging"),
        RuleDefinition("PY_SETUP_PY_NETWORK_ACCESS", "python_packaging"),
    )


_RULE_DEFINITIONS = _definitions()
RULE_DEFINITIONS = MappingProxyType({definition.id: definition for definition in _RULE_DEFINITIONS})
RULE_IDS = frozenset(RULE_DEFINITIONS)

if len(RULE_DEFINITIONS) != len(_RULE_DEFINITIONS):
    raise RuntimeError("Trojaino rule registry contains duplicate IDs")


def unregistered_rule_ids(findings: Iterable[object]) -> set[str]:
    """Return finding IDs that cannot be represented by the public contract."""
    return {
        str(getattr(finding, "id", ""))
        for finding in findings
        if getattr(finding, "id", None) not in RULE_DEFINITIONS
    }
