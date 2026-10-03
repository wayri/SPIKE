# SPDX-License-Identifier: Apache-2.0
"""Confined file operations for the integrated Python workspace."""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


MAX_FILE_BYTES = 512_000
MAX_DIRECTORY_ENTRIES = 500
MAX_GIT_OUTPUT_BYTES = 512_000
MAX_WORKTREES = 256
GIT_WORKTREE_TIMEOUT_SECONDS = 5.0
READABLE_SUFFIXES = {
    ".py", ".pyi", ".txt", ".md", ".json", ".toml", ".yaml", ".yml",
    ".csv", ".tsv", ".ini", ".cfg",
}
LISTED_SUFFIXES = {".py"}
SKIPPED_NAMES = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".venv", "venv",
    "__pycache__", "node_modules", "target", "dist", "build", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "coverage", ".coverage",
}


def default_workspace_root() -> Path:
    configured = os.environ.get("SPIKE_WORKSPACE")
    return Path(configured).expanduser() if configured else Path(__file__).resolve().parents[2]


def _reject_symlinks(path: Path, *, include_leaf: bool = True) -> None:
    candidate = path if include_leaf else path.parent
    parts = candidate.parts
    if not parts:
        return
    current = Path(parts[0])
    for part in parts[1:]:
        current /= part
        if current.exists() and current.is_symlink():
            raise ValueError("Python workspace paths may not traverse symbolic links.")


def _root(value: Any) -> Path:
    if value is None or value == "":
        path = default_workspace_root()
    elif isinstance(value, str):
        path = Path(value).expanduser()
    else:
        raise TypeError("Python workspace root must be a path string.")
    if not path.is_absolute():
        path = default_workspace_root() / path
    _reject_symlinks(path)
    resolved = path.resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("Python workspace root must be an existing directory.")
    return resolved


def _relative_path(value: Any) -> Path:
    if value is None or value == "":
        return Path()
    if not isinstance(value, str):
        raise TypeError("Python workspace path must be a string.")
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise ValueError("Python workspace path must stay below the selected root.")
    return path


def _target(root: Path, value: Any, *, existing: bool) -> tuple[Path, str]:
    relative = _relative_path(value)
    candidate = root / relative
    _reject_symlinks(candidate, include_leaf=existing)
    resolved = candidate.resolve(strict=existing)
    try:
        relative_text = resolved.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("Python workspace path escapes the selected root.") from exc
    return resolved, relative_text


def resolve_script_paths(params: dict[str, Any]) -> tuple[Path, Path]:
    """Resolve a script below its selected working directory without symlinks."""
    raw_working = params.get("working_directory")
    raw_filename = params.get("filename") or "spike_script.py"
    if not isinstance(raw_filename, str):
        raise TypeError("Python script filename must be a path string.")
    supplied_filename = Path(raw_filename).expanduser()
    if raw_working in (None, ""):
        working = _root(str(supplied_filename.parent) if supplied_filename.is_absolute() else None)
    elif isinstance(raw_working, str):
        working = _root(raw_working)
    else:
        raise TypeError("Python script working_directory must be a path string.")
    filename_candidate = supplied_filename if supplied_filename.is_absolute() else working / supplied_filename
    filename_candidate = Path(os.path.abspath(filename_candidate))
    try:
        filename_candidate.relative_to(working)
    except ValueError as exc:
        raise ValueError("Python script filename must stay inside its working directory.") from exc
    _reject_symlinks(filename_candidate, include_leaf=filename_candidate.exists())
    filename = filename_candidate.resolve(strict=False)
    if filename.suffix.lower() != ".py":
        raise ValueError("Python script filename must end in .py.")
    return working, filename


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_file(path: Path, relative: str) -> dict[str, Any]:
    if path.suffix.lower() not in READABLE_SUFFIXES:
        raise ValueError("Only editable Python and text files can be read in the workspace.")
    if not path.is_file():
        raise ValueError("Python workspace path is not a file.")
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError("Python workspace files are limited to 512 KB.")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Python workspace files are limited to 512 KB.")
    if b"\x00" in data:
        raise ValueError("Binary files cannot be opened in the Python workspace.")
    try:
        contents = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Python workspace files must be UTF-8 text.") from exc
    return {"path": relative, "name": path.name, "contents": contents, "sha256": _sha256(data)}


def _list_directory(root: Path, path: Path, relative: str) -> dict[str, Any]:
    if not path.is_dir():
        raise ValueError("Python workspace path is not a directory.")
    entries: list[dict[str, Any]] = []
    truncated = False
    candidates: list[tuple[bool, str, int]] = []
    with os.scandir(path) as iterator:
        for child in iterator:
            if child.name in SKIPPED_NAMES or child.is_symlink():
                continue
            is_directory = child.is_dir(follow_symlinks=False)
            if not is_directory and Path(child.name).suffix.lower() not in LISTED_SUFFIXES:
                continue
            if len(candidates) >= MAX_DIRECTORY_ENTRIES:
                truncated = True
                break
            size = 0 if is_directory else child.stat(follow_symlinks=False).st_size
            candidates.append((is_directory, child.name, size))
    candidates.sort(key=lambda item: (not item[0], item[1].casefold()))
    for is_directory, name, size in candidates:
        child_relative = (path / name).relative_to(root).as_posix()
        entries.append({
            "name": name, "path": child_relative,
            "kind": "directory" if is_directory else "file", "size": size,
        })
    return {"root": str(root), "path": relative, "entries": entries, "truncated": truncated}


def _write_file(path: Path, relative: str, contents: Any, expected: Any) -> dict[str, Any]:
    if path.suffix.lower() != ".py":
        raise ValueError("The Python workspace can only save .py files.")
    if not isinstance(contents, str):
        raise TypeError("Python workspace write contents must be a string.")
    data = contents.encode("utf-8")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Python workspace files are limited to 512 KB.")
    if not path.parent.is_dir():
        raise ValueError("The destination directory does not exist.")
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise ValueError("Python workspace destination must be a regular file.")
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError("expected_sha256 is required when overwriting a workspace file.")
        with path.open("rb") as stream:
            current = stream.read(MAX_FILE_BYTES + 1)
        if len(current) > MAX_FILE_BYTES:
            raise ValueError("Existing Python workspace file exceeds the 512 KB editor limit.")
        if _sha256(current) != expected.lower():
            raise FileExistsError("The workspace file changed since it was opened.")
    elif expected not in (None, ""):
        raise FileExistsError("The workspace file does not exist for the supplied expected_sha256.")
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
    return {"path": relative, "name": path.name, "sha256": _sha256(data), "size": len(data)}


def _validated_worktree_path(path_text: str) -> Path | None:
    candidate = Path(path_text)
    if not candidate.is_absolute():
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return resolved if resolved.is_dir() else None


def _parse_worktrees(data: bytes) -> list[dict[str, Any]]:
    if len(data) > MAX_GIT_OUTPUT_BYTES:
        raise ValueError("Git worktree inventory exceeded the 512 KB output limit.")
    records = data.split(b"\0\0")
    if records and records[-1] == b"":
        records.pop()
    if len(records) > MAX_WORKTREES:
        raise ValueError("Git worktree inventory exceeded the 256 worktree limit.")

    worktrees: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for record in records:
        fields: dict[bytes, bytes] = {}
        flags: set[bytes] = set()
        for field in record.split(b"\0"):
            if not field:
                continue
            key, separator, value = field.partition(b" ")
            if separator:
                fields[key] = value
            else:
                flags.add(key)
        raw_path = fields.get(b"worktree")
        if raw_path is None or len(raw_path) > 32_768:
            continue
        try:
            path_text = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            continue
        resolved = _validated_worktree_path(path_text)
        if resolved is None:
            continue
        normalized = os.path.normcase(str(resolved))
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)

        item: dict[str, Any] = {"path": str(resolved)}
        raw_head = fields.get(b"HEAD")
        if raw_head is not None:
            head = raw_head.decode("ascii", errors="ignore")
            if re.fullmatch(r"[0-9a-fA-F]{4,128}", head):
                item["head"] = head.lower()
        raw_branch = fields.get(b"branch")
        if raw_branch is not None and len(raw_branch) <= 4096:
            try:
                item["branch"] = raw_branch.decode("utf-8")
            except UnicodeDecodeError:
                pass
        if b"detached" in flags:
            item["detached"] = True
        if b"locked" in flags or b"locked" in fields:
            item["locked"] = True
        if b"prunable" in flags or b"prunable" in fields:
            item["prunable"] = True
        worktrees.append(item)
    return worktrees


def _list_worktrees(root: Path) -> dict[str, Any]:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    environment["GIT_TERMINAL_PROMPT"] = "0"
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain", "-z"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=GIT_WORKTREE_TIMEOUT_SECONDS,
            check=False,
            shell=False,
            env=environment,
        )
    except FileNotFoundError:
        return {
            "root": str(root), "available": False, "worktrees": [],
            "message": "Git is not available on this system.",
        }
    except subprocess.TimeoutExpired:
        return {
            "root": str(root), "available": False, "worktrees": [],
            "message": "Git worktree inventory timed out.",
        }
    except OSError:
        return {
            "root": str(root), "available": False, "worktrees": [],
            "message": "Git worktree inventory could not be started.",
        }
    if completed.returncode != 0:
        return {
            "root": str(root), "available": False, "worktrees": [],
            "message": "The selected root is not an available Git worktree.",
        }
    try:
        worktrees = _parse_worktrees(completed.stdout)
    except ValueError as exc:
        return {
            "root": str(root), "available": False, "worktrees": [],
            "message": str(exc),
        }
    return {"root": str(root), "available": True, "worktrees": worktrees}


def python_workspace_files(params: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(params, dict):
        raise TypeError("Python workspace file parameters must be an object.")
    action = params.get("action")
    if action not in {"list", "read", "write", "worktrees"}:
        raise ValueError("Python workspace file action must be list, read, write, or worktrees.")
    root = _root(params.get("root"))
    if action == "worktrees":
        return {"contract": "spike/python-workspace-files/v1", **_list_worktrees(root)}
    path, relative = _target(root, params.get("path"), existing=action != "write" or (root / _relative_path(params.get("path"))).exists())
    if action == "list":
        result = _list_directory(root, path, relative)
    elif action == "read":
        result = {"root": str(root), **_read_file(path, relative)}
    else:
        result = {"root": str(root), **_write_file(
            path, relative, params.get("contents"), params.get("expected_sha256"),
        )}
    return {"contract": "spike/python-workspace-files/v1", **result}


__all__ = ["python_workspace_files", "default_workspace_root", "resolve_script_paths"]
