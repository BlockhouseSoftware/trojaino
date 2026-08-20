from __future__ import annotations

from pathlib import Path

TEXT_EXTENSIONS = {
    "", ".cjs", ".conf", ".css", ".env", ".html", ".js", ".json", ".jsx",
    ".lock", ".md", ".mjs", ".py", ".sh", ".toml", ".ts", ".tsx", ".txt",
    ".yaml", ".yml", ".dockerfile",
}
TEXT_FILENAMES = {
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "package.json",
    "AGENTS.md", "CLAUDE.md", ".windsurfrules",
}
SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", ".next", ".venv", "venv", "__pycache__",
    ".pytest_cache", ".mypy_cache", "coverage", ".turbo",
}
RELEASE_EXCLUDED_ROOTS = {"tests", "reference", "docs", "examples", "example"}
SCAN_PROFILES = {"default", "release"}


def should_scan(path: Path) -> bool:
    if any(part in SKIP_DIRS for part in path.parts):
        return False
    return path.name in TEXT_FILENAMES or path.suffix.lower() in TEXT_EXTENSIONS


def is_in_release_artifact(path: Path, root: Path) -> bool:
    """Exclude development-only material from a checked-in release profile."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    return not relative.parts or relative.parts[0].lower() not in RELEASE_EXCLUDED_ROOTS


def iter_files(root: Path, profile: str = "default") -> list[Path]:
    if profile not in SCAN_PROFILES:
        raise ValueError(f"unknown scan profile: {profile}")
    if root.is_file():
        return [root] if should_scan(root) else []
    files: list[Path] = []
    for path in root.rglob("*"):
        if (
            path.is_file()
            and should_scan(path)
            and (profile != "release" or is_in_release_artifact(path, root))
        ):
            files.append(path)
    return sorted(files)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None
    except OSError:
        return None


def line_number(text: str, needle: str) -> int | None:
    idx = text.find(needle)
    if idx < 0:
        return None
    return text.count("\n", 0, idx) + 1


def line_for_index(text: str, idx: int) -> int:
    return text.count("\n", 0, max(idx, 0)) + 1


def first_matching_line(text: str, predicate) -> tuple[int, str] | None:
    for index, line in enumerate(text.splitlines(), start=1):
        if predicate(line):
            return index, line.strip()
    return None
