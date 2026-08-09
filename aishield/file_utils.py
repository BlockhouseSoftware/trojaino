from __future__ import annotations

import os
import stat
import time
from pathlib import Path

from aishield.models import ScanIssue

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


def relpath_for_issue(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def iter_files(
    root: Path,
    profile: str = "default",
    *,
    max_files: int = 10_000,
    max_entries: int = 40_000,
    max_depth: int = 50,
    deadline: float | None = None,
    issues: list[ScanIssue] | None = None,
) -> list[Path]:
    """Enumerate regular files without following child symbolic links."""
    if profile not in SCAN_PROFILES:
        raise ValueError(f"unknown scan profile: {profile}")
    issue_list = issues if issues is not None else []
    if root.is_symlink():
        issue_list.append(ScanIssue("symlink_rejected", "Selected target is a symbolic link", root.name))
        return []
    if root.is_file():
        return [root] if should_scan(root) else []
    files: list[Path] = []
    entries_seen = 0
    stack = [(root, 0)]
    while stack:
        if deadline is not None and time.monotonic() >= deadline:
            issue_list.append(ScanIssue("elapsed_time_limit", "Elapsed scan-time limit was reached"))
            break
        directory, depth = stack.pop()
        try:
            entries = os.scandir(directory)
        except OSError as exc:
            issue_list.append(ScanIssue(
                "directory_unreadable",
                f"Directory could not be enumerated: {exc.__class__.__name__}",
                relpath_for_issue(directory, root),
            ))
            continue
        with entries:
            for entry in entries:
                if entries_seen >= max_entries:
                    issue_list.append(ScanIssue("entry_count_limit", "Maximum filesystem-entry count was exceeded"))
                    return sorted(files)
                entries_seen += 1
                path = Path(entry.path)
                rel = relpath_for_issue(path, root)
                try:
                    if entry.is_symlink():
                        issue_list.append(ScanIssue("symlink_rejected", "Child symbolic link was not followed", rel))
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name in SKIP_DIRS:
                            continue
                        child_depth = depth + 1
                        if child_depth > max_depth:
                            issue_list.append(ScanIssue("depth_limit", "Maximum directory depth was exceeded", rel))
                            continue
                        if profile == "release" and child_depth == 1 and entry.name.lower() in RELEASE_EXCLUDED_ROOTS:
                            continue
                        stack.append((path, child_depth))
                        continue
                    if not entry.is_file(follow_symlinks=False) or not should_scan(path):
                        continue
                except OSError as exc:
                    issue_list.append(ScanIssue(
                        "file_unreadable",
                        f"Filesystem entry could not be inspected: {exc.__class__.__name__}",
                        rel,
                    ))
                    continue
                if len(files) >= max_files:
                    issue_list.append(ScanIssue("file_count_limit", "Maximum scanned-file count was exceeded"))
                    return sorted(files)
                files.append(path)
    return sorted(files)


def read_text(path: Path) -> str | None:
    """Compatibility helper: UTF-8 is strict and malformed bytes are unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def read_bytes_no_symlink(
    path: Path,
    root: Path,
    max_bytes: int,
    expected_root_identity: tuple[int, int] | None = None,
    expected_file_identity: tuple[int, int] | None = None,
) -> tuple[bytes | None, str | None]:
    """Read a contained regular file without traversing child symlinks.

    On POSIX, walk from an already-open root directory using ``openat``-style
    ``dir_fd`` calls. This anchors every path component to the selected root
    and closes the check/read race left by resolving a path before opening it.
    Other platforms use a best-effort lstat/open/fstat/revalidation sequence.
    """
    try:
        relative = path.relative_to(root)
        if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
            return None, "outside_root"
    except (OSError, ValueError):
        return None, "outside_root"

    def read_fd(fd: int) -> tuple[bytes | None, str | None]:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            return None, "not_regular_file"
        data = bytearray()
        while len(data) <= max_bytes:
            chunk = os.read(fd, min(65_536, max_bytes + 1 - len(data)))
            if not chunk:
                return bytes(data), None
            data.extend(chunk)
        return None, "file_size_limit"

    supports_anchored_open = (
        os.open in getattr(os, "supports_dir_fd", set())
        and hasattr(os, "O_DIRECTORY")
        and hasattr(os, "O_NOFOLLOW")
    )
    if supports_anchored_open:
        try:
            root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError:
            return None, "outside_root"
        current_fd = root_fd
        try:
            root_info = os.fstat(root_fd)
            if expected_root_identity is not None and (root_info.st_dev, root_info.st_ino) != expected_root_identity:
                return None, "outside_root"
            current_fd = root_fd
            for part in relative.parts[:-1]:
                next_fd = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=current_fd,
                )
                if current_fd != root_fd:
                    os.close(current_fd)
                current_fd = next_fd
            file_fd = os.open(
                relative.parts[-1],
                os.O_RDONLY | os.O_NOFOLLOW,
                dir_fd=current_fd,
            )
            try:
                file_info = os.fstat(file_fd)
                if expected_file_identity is not None and (file_info.st_dev, file_info.st_ino) != expected_file_identity:
                    return None, "outside_root"
                return read_fd(file_fd)
            finally:
                os.close(file_fd)
        except OSError:
            return None, "unreadable"
        finally:
            if current_fd != root_fd:
                os.close(current_fd)
            os.close(root_fd)

    # Best effort for platforms without directory-relative no-follow opens.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        root_before = root.lstat()
        if stat.S_ISLNK(root_before.st_mode):
            return None, "outside_root"
        if expected_root_identity is not None and (root_before.st_dev, root_before.st_ino) != expected_root_identity:
            return None, "outside_root"
        resolved_root = root.resolve(strict=True)
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode):
            return None, "unreadable"
        resolved = path.resolve(strict=True)
        resolved.relative_to(resolved_root)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            if expected_file_identity is not None and (opened.st_dev, opened.st_ino) != expected_file_identity:
                return None, "outside_root"
            after = path.lstat()
            root_after = root.lstat()
            resolved_after = path.resolve(strict=True)
            resolved_after.relative_to(resolved_root)
            if (
                stat.S_ISLNK(root_after.st_mode)
                or expected_root_identity is not None
                and (root_after.st_dev, root_after.st_ino) != expected_root_identity
                or stat.S_ISLNK(after.st_mode)
                or (opened.st_dev, opened.st_ino) != (after.st_dev, after.st_ino)
            ):
                return None, "unreadable"
            return read_fd(fd)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None, "unreadable"


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
