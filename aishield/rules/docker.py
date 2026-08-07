from __future__ import annotations

import re
from pathlib import Path

from aishield.file_utils import first_matching_line
from aishield.models import Finding, relpath

DOCKER_NAMES = {"Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"}
PORT_RE = re.compile(r"['\"]?(0\.0\.0\.0:)?(2375|2376|5432|6379|27017|3306|9200|15672|8080|8000):")


def scan_docker(root: Path, files: list[Path], texts: dict[Path, str]) -> list[Finding]:
    findings: list[Finding] = []
    for path in files:
        if path.name not in DOCKER_NAMES:
            continue
        text = texts.get(path, "")
        rel = relpath(path, root)
        checks = [
            ("DOCKER_PRIVILEGED_CONTAINER", "high", "Container runs in privileged mode", lambda l: "privileged:" in l and "true" in l.lower(), "Privileged containers can escape normal container isolation and access host resources.", "Remove privileged mode unless there is a documented, reviewed need."),
            ("DOCKER_SOCKET_MOUNT", "critical", "Docker socket is mounted into a container", lambda l: "/var/run/docker.sock" in l, "Docker socket access often grants root-equivalent control of the host.", "Do not mount the Docker socket into untrusted or AI-generated projects."),
            ("DOCKER_HOME_MOUNT", "high", "Host home directory appears mounted into a container", lambda l: re.search(r"[-:]\s*(~|\$HOME|/Users/|/home/).*(/host|:/)", l), "Mounting the host home directory can expose SSH keys, cloud credentials, and private files.", "Mount only the specific project subdirectory required by the service."),
            ("DOCKER_RUNS_AS_ROOT", "medium", "Dockerfile does not set a non-root USER", lambda l: l.strip().upper().startswith("FROM "), "Containers run as root by default unless a USER is set later in the Dockerfile.", "Add a non-root USER for runtime stages when possible."),
        ]
        for rule_id, severity, title, predicate, why, rec in checks:
            if rule_id == "DOCKER_RUNS_AS_ROOT" and path.name != "Dockerfile":
                continue
            if rule_id == "DOCKER_RUNS_AS_ROOT" and re.search(r"^\s*USER\s+", text, re.M):
                continue
            match = first_matching_line(text, predicate)
            if match:
                line, evidence = match
                disposition = "actionable" if rule_id == "DOCKER_SOCKET_MOUNT" else "review"
                findings.append(Finding(rule_id, severity, "high", title, rel, line, evidence, why, rec, disposition=disposition))
        for match in PORT_RE.finditer(text):
            findings.append(Finding(
                id="DOCKER_ADMIN_PORT_EXPOSED",
                severity="medium",
                confidence="medium",
                title="Sensitive service/admin port appears exposed",
                file=rel,
                line=text.count("\n", 0, match.start()) + 1,
                evidence=match.group(0),
                why_it_matters="Databases, Docker APIs, search clusters, and admin UIs should not be exposed casually from a generated project.",
                recommendation="Bind sensitive ports to localhost, add authentication, or remove the mapping before running.",
            ))
    return findings
