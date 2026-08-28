"""Bounded, static pre-run checks for Python packaging metadata."""
from __future__ import annotations

import ast
import tomllib
from pathlib import Path
from typing import Mapping

from trojaino.file_utils import line_number
from trojaino.models import Finding, relpath
from trojaino.rules.budget import BudgetedList, RuleBudget


_DIRECT_REFERENCE_PREFIXES = (
    "http://", "https://", "git+", "git://", "ssh://", "file:", "./", "../", "/",
)
_NETWORK_CALLS = {
    "urllib.request.urlopen",
    "urllib.request.urlretrieve",
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.patch",
    "requests.delete",
    "httpx.get",
    "httpx.post",
    "httpx.put",
    "httpx.patch",
    "httpx.delete",
}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _direct_reference(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    dependency = value.strip()
    source = dependency.partition(" @ ")[2].strip() or dependency
    return source if source.lower().startswith(_DIRECT_REFERENCE_PREFIXES) else None


def _project_dependency_values(document: Mapping[str, object]) -> list[str]:
    project = document.get("project")
    if not isinstance(project, dict):
        return []
    values = list(project.get("dependencies", [])) if isinstance(project.get("dependencies"), list) else []
    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for group in optional.values():
            if isinstance(group, list):
                values.extend(group)
    return [value for value in values if isinstance(value, str)]


def _build_requirement_values(document: Mapping[str, object]) -> list[str]:
    build_system = document.get("build-system")
    if not isinstance(build_system, dict):
        return []
    requires = build_system.get("requires")
    return [value for value in requires if isinstance(value, str)] if isinstance(requires, list) else []


def _has_extra_index(document: object) -> bool:
    if isinstance(document, dict):
        for key, value in document.items():
            if isinstance(key, str) and key in {"extra-index-url", "extra_index_url"} and value:
                return True
            if _has_extra_index(value):
                return True
        return False
    if isinstance(document, list):
        return any(_has_extra_index(value) for value in document)
    return False


class _ModuleLevelNetworkCalls(ast.NodeVisitor):
    def __init__(self) -> None:
        self.calls: list[ast.Call] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Call(self, node: ast.Call) -> None:
        if _call_name(node.func).lower() in _NETWORK_CALLS:
            self.calls.append(node)
        self.generic_visit(node)


def _append_direct_dependency(
    findings: BudgetedList[Finding],
    *,
    rule_id: str,
    title: str,
    rel: str,
    text: str,
    dependency: str,
) -> None:
    findings.append(Finding(
        id=rule_id,
        severity="medium",
        confidence="high",
        title=title,
        file=rel,
        line=line_number(text, dependency),
        evidence=dependency,
        why_it_matters="Direct URLs, VCS references, and local paths can bypass ordinary package-index review and make build inputs harder to reproduce.",
        recommendation="Pin and review the exact source, prefer a trusted registry artifact when possible, and document why the direct dependency is required.",
    ))


def scan_python_packaging(
    root: Path,
    files: list[Path],
    texts: dict[Path, str],
    budget: RuleBudget | None = None,
) -> list[Finding]:
    """Inspect Python build metadata without importing, installing, or executing it."""
    findings: BudgetedList[Finding] = BudgetedList(budget)
    for path in files:
        findings.checkpoint()
        text = texts.get(path, "")
        rel = relpath(path, root)
        if path.name == "pyproject.toml":
            try:
                document = tomllib.loads(text)
            except tomllib.TOMLDecodeError:
                findings.append(Finding(
                    id="PYPROJECT_TOML_PARSE_ERROR",
                    severity="medium",
                    confidence="high",
                    title="pyproject.toml could not be parsed",
                    file=rel,
                    line=None,
                    evidence="Invalid TOML in Python project metadata",
                    why_it_matters="Malformed build metadata can hide dependency and build-backend behavior from static inspection.",
                    recommendation="Fix pyproject.toml and rescan before installing or building the project.",
                ))
                continue

            for dependency in _build_requirement_values(document):
                findings.checkpoint()
                if _direct_reference(dependency):
                    _append_direct_dependency(
                        findings,
                        rule_id="PYPROJECT_DIRECT_BUILD_REQUIREMENT",
                        title="Python build requirement uses a direct source reference",
                        rel=rel,
                        text=text,
                        dependency=dependency,
                    )
            for dependency in _project_dependency_values(document):
                findings.checkpoint()
                if _direct_reference(dependency):
                    _append_direct_dependency(
                        findings,
                        rule_id="PYPROJECT_DIRECT_RUNTIME_DEPENDENCY",
                        title="Python runtime dependency uses a direct source reference",
                        rel=rel,
                        text=text,
                        dependency=dependency,
                    )
            if _has_extra_index(document):
                findings.append(Finding(
                    id="PYPROJECT_EXTRA_PACKAGE_INDEX",
                    severity="medium",
                    confidence="high",
                    title="Python project configures an extra package index",
                    file=rel,
                    line=line_number(text, "extra-index-url") or line_number(text, "extra_index_url"),
                    evidence="extra package index configured",
                    why_it_matters="Extra indexes can change dependency resolution and expose projects to dependency-confusion risks when package ownership is unclear.",
                    recommendation="Use a single trusted index where possible; otherwise pin dependencies and document the trusted package namespace for every extra index.",
                ))
        elif path.name == "setup.py":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            visitor = _ModuleLevelNetworkCalls()
            visitor.visit(tree)
            for call in visitor.calls:
                findings.checkpoint()
                evidence = ast.get_source_segment(text, call) or "network call"
                findings.append(Finding(
                    id="PY_SETUP_PY_NETWORK_ACCESS",
                    severity="high",
                    confidence="high",
                    title="setup.py performs network access during build or install",
                    file=rel,
                    line=getattr(call, "lineno", None),
                    evidence=evidence.strip(),
                    why_it_matters="setup.py is executed by package tooling; module-level network access can fetch or run unreviewed content before an application is installed.",
                    recommendation="Remove install-time network access and vendor or publish reviewed, pinned build inputs through a trusted registry.",
                    disposition="actionable",
                ))
    return findings
