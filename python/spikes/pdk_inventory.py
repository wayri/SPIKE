# SPDX-License-Identifier: Apache-2.0
"""Bounded, inert inspection of locally installed open-PDK SPICE libraries.

This module reads text and computes provenance hashes.  It never installs a
PDK, invokes a model, or claims simulator compatibility or physical validity.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path, PurePath
from typing import Any


CONTRACT = "spikes/open-pdk-inventory/v1"
MAX_FILES = 128
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024

_CATALOG = (
    {
        "id": "sky130",
        "name": "SkyWater SKY130",
        "default_entry": "sky130A/libs.tech/ngspice/sky130.lib.spice",
        "official_url": "https://github.com/google/skywater-pdk",
    },
    {
        "id": "gf180mcu",
        "name": "GlobalFoundries GF180MCU",
        "default_entry": "gf180mcuD/libs.tech/ngspice/gf180mcu.lib.spice",
        "official_url": "https://github.com/google/gf180mcu-pdk",
    },
    {
        "id": "ihp_sg13g2",
        "name": "IHP SG13G2",
        "default_entry": "ihp-sg13g2/libs.tech/ngspice/models/cornerMOSlv.lib",
        "official_url": "https://github.com/IHP-GmbH/IHP-Open-PDK",
    },
)
_CATALOG_BY_ID = {item["id"]: item for item in _CATALOG}
_ALIASES = {"sky130a": "sky130", "gf180mcud": "gf180mcu", "sg13g2": "ihp_sg13g2", "ihp-sg13g2": "ihp_sg13g2"}
_TOKEN = re.compile(r'''"[^"]*"|'[^']*'|[^\s]+''')
_LICENSE_NAMES = ("COPYING", "LICENSE.txt", "LICENSE")


class PdkInventoryError(ValueError):
    """The requested inspection cannot be performed safely."""


def catalog() -> list[dict[str, Any]]:
    """Return supported installation layouts, without probing the host."""
    return [
        {
            **item,
            "inspection": "local_files_only",
            "model_readiness": "review_only",
            "qualified": False,
        }
        for item in _CATALOG
    ]


def _unquote(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _relative_file(root: Path, candidate: Path, *, label: str) -> tuple[Path, str]:
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise PdkInventoryError(f"{label} is missing: {candidate}") from exc
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise PdkInventoryError(f"{label} escapes the selected PDK root: {candidate}") from exc
    if not resolved.is_file():
        raise PdkInventoryError(f"{label} is not a regular file: {candidate}")
    return resolved, relative.as_posix()


def _safe_entry(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or not value.strip() or any(part == ".." for part in PurePath(value).parts):
        raise PdkInventoryError("entry must be a non-empty relative path without parent traversal")
    return path


def _choose_root(pdk_id: str, supplied_root: Path, entry: Path) -> tuple[Path, Path, str]:
    resolved_root = supplied_root.resolve(strict=True)
    if not resolved_root.is_dir():
        raise PdkInventoryError("root must be an existing directory")
    candidates = (resolved_root, resolved_root / pdk_id)
    for candidate in candidates:
        try:
            selected = candidate.resolve(strict=True)
        except OSError:
            continue
        try:
            selected.relative_to(resolved_root)
        except ValueError as exc:
            raise PdkInventoryError(f"candidate PDK root escapes the supplied root: {candidate}") from exc
        target = selected / entry
        if not target.exists():
            continue
        try:
            exact, relative = _relative_file(selected, target, label="entry")
        except PdkInventoryError:
            raise
        return selected, exact, relative
    attempted = ", ".join(str(candidate / entry) for candidate in candidates)
    raise PdkInventoryError(f"model entry is missing; tried: {attempted}")


def _logical_lines(text: str) -> list[tuple[int, str]]:
    logical: list[tuple[int, str]] = []
    for number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("+") and logical:
            first, previous = logical[-1]
            logical[-1] = (first, previous + " " + stripped[1:].strip())
        else:
            logical.append((number, stripped))
    return logical


def _tokens(line: str) -> list[str]:
    return [_unquote(token) for token in _TOKEN.findall(line)]


def _parameter(token: str) -> dict[str, str | None]:
    name, separator, default = token.partition("=")
    return {"name": name, "default": default if separator else None}


def _read_at_most(path: Path, limit: int) -> bytes:
    with path.open("rb") as stream:
        return stream.read(limit + 1)


def inspect(pdk_id: str, root: str | Path, entry: str | Path | None = None) -> dict[str, Any]:
    """Inspect one local PDK library and its contained textual dependencies.

    Dependency references are followed only inside the selected root.  Missing
    or unreadable dependencies are retained as issues; containment violations
    are rejected.  The result is inventory evidence, never execution evidence.
    """
    normalized_id = _ALIASES.get(str(pdk_id).lower(), str(pdk_id).lower())
    descriptor = _CATALOG_BY_ID.get(normalized_id)
    if descriptor is None:
        raise PdkInventoryError(f"unknown PDK id: {pdk_id}")
    relative_entry = _safe_entry(str(entry if entry is not None else descriptor["default_entry"]))
    selected_root, entry_path, entry_relative = _choose_root(normalized_id, Path(root), relative_entry)

    files: list[dict[str, Any]] = []
    dependencies: list[dict[str, Any]] = []
    sections: list[str] = []
    section_declarations: list[dict[str, Any]] = []
    subcircuits: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    visited: set[Path] = set()
    queued: set[Path] = {entry_path}
    queue: list[tuple[Path, str]] = [(entry_path, "entry")]
    total_bytes = 0

    while queue:
        path, role = queue.pop(0)
        queued.discard(path)
        if path in visited:
            continue
        if len(visited) >= MAX_FILES:
            issues.append({"code": "file_limit", "message": f"inspection stopped at {MAX_FILES} files"})
            break
        exact, relative = _relative_file(selected_root, path, label="dependency")
        size = exact.stat().st_size
        if size > MAX_FILE_BYTES:
            if role == "entry":
                raise PdkInventoryError(f"entry exceeds the {MAX_FILE_BYTES}-byte file limit")
            issues.append({"code": "file_too_large", "path": relative, "bytes": size, "limit": MAX_FILE_BYTES})
            visited.add(exact)
            continue
        if total_bytes + size > MAX_TOTAL_BYTES:
            if role == "entry":
                raise PdkInventoryError(f"entry exceeds the {MAX_TOTAL_BYTES}-byte cumulative limit")
            issues.append({"code": "total_size_limit", "path": relative, "bytes": size, "limit": MAX_TOTAL_BYTES})
            break
        data = _read_at_most(exact, min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total_bytes))
        if len(data) > MAX_FILE_BYTES or total_bytes + len(data) > MAX_TOTAL_BYTES:
            if role == "entry":
                raise PdkInventoryError("entry changed while reading and exceeds an inspection limit")
            issues.append({"code": "file_changed_over_limit", "path": relative})
            visited.add(exact)
            continue
        total_bytes += len(data)
        visited.add(exact)
        files.append({"path": relative, "role": role, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            issues.append({"code": "text_decode_error", "path": relative, "line": None, "message": str(exc)})
            continue

        open_sections: list[tuple[str, int]] = []
        for line_number, logical in _logical_lines(text):
            tokens = _tokens(logical)
            if not tokens:
                continue
            directive = tokens[0].lower()
            if directive == ".lib" and len(tokens) == 2:
                name = tokens[1]
                sections.append(name)
                section_declarations.append({"name": name, "path": relative, "line": line_number})
                open_sections.append((name, line_number))
                continue
            if directive == ".endl":
                if not open_sections:
                    issues.append({"code": "unmatched_endl", "path": relative, "line": line_number})
                else:
                    expected, _ = open_sections.pop()
                    if len(tokens) >= 2 and tokens[1].lower() != expected.lower():
                        issues.append({"code": "section_name_mismatch", "path": relative, "line": line_number,
                                       "expected": expected, "observed": tokens[1]})
                continue
            if directive == ".subckt" and len(tokens) >= 2:
                arguments = tokens[2:]
                split = next((index for index, token in enumerate(arguments)
                              if token.lower() == "params:" or "=" in token), len(arguments))
                parameter_tokens = arguments[split:]
                if parameter_tokens and parameter_tokens[0].lower() == "params:":
                    parameter_tokens = parameter_tokens[1:]
                subcircuits.append({
                    "name": tokens[1], "pins": arguments[:split],
                    "parameters": [_parameter(token) for token in parameter_tokens],
                    "path": relative, "line": line_number,
                })
                continue
            reference: str | None = None
            selected_section: str | None = None
            if directive == ".include" and len(tokens) >= 2:
                reference = tokens[1]
            elif directive == ".lib" and len(tokens) >= 3:
                reference, selected_section = tokens[1], tokens[2]
            if reference is None:
                continue
            record: dict[str, Any] = {
                "source": relative, "line": line_number, "directive": directive,
                "reference": reference, "section": selected_section,
            }
            if "$" in reference or "{" in reference or "}" in reference:
                record.update(status="unresolved", error="variable_or_expression_path")
                dependencies.append(record)
                issues.append({"code": "unresolved_dependency", **record})
                continue
            candidate = exact.parent / Path(reference)
            # Path accepts forward slashes on every supported host; reject a
            # Windows absolute/reference form even when inspecting on POSIX.
            if Path(reference).is_absolute() or re.match(r"^[A-Za-z]:[\\/]", reference):
                raise PdkInventoryError(f"dependency uses an absolute path at {relative}:{line_number}")
            try:
                resolved = candidate.resolve(strict=True)
            except OSError:
                record.update(status="unresolved", error="missing")
                dependencies.append(record)
                issues.append({"code": "unresolved_dependency", **record})
                continue
            try:
                dependency_relative = resolved.relative_to(selected_root).as_posix()
            except ValueError as exc:
                raise PdkInventoryError(f"dependency escapes the selected PDK root at {relative}:{line_number}") from exc
            if not resolved.is_file():
                record.update(status="unresolved", error="not_a_regular_file")
                dependencies.append(record)
                issues.append({"code": "unresolved_dependency", **record})
                continue
            record.update(status="available", path=dependency_relative)
            dependencies.append(record)
            if resolved not in visited and resolved not in queued:
                queue.append((resolved, "dependency"))
                queued.add(resolved)
        for name, line_number in open_sections:
            issues.append({"code": "unclosed_lib_section", "path": relative, "line": line_number, "section": name})

    licenses: list[dict[str, Any]] = []
    for name in _LICENSE_NAMES:
        candidate = selected_root / name
        if not candidate.exists():
            continue
        exact, relative = _relative_file(selected_root, candidate, label="license file")
        size = exact.stat().st_size
        if size > MAX_FILE_BYTES or total_bytes + size > MAX_TOTAL_BYTES or len(visited) >= MAX_FILES:
            issues.append({"code": "license_not_hashed_within_limits", "path": relative, "bytes": size})
            continue
        data = _read_at_most(exact, min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total_bytes))
        if len(data) > MAX_FILE_BYTES or total_bytes + len(data) > MAX_TOTAL_BYTES:
            issues.append({"code": "license_changed_over_limit", "path": relative})
            continue
        total_bytes += len(data)
        visited.add(exact)
        licenses.append({"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                         "interpretation": "not_performed"})

    by_name: dict[str, list[dict[str, Any]]] = {}
    for declaration in subcircuits:
        by_name.setdefault(declaration["name"].lower(), []).append(declaration)
    duplicates = [
        {"name": declarations[0]["name"], "declarations": [
            {"path": item["path"], "line": item["line"]} for item in declarations
        ]}
        for declarations in by_name.values() if len(declarations) > 1
    ]
    unique_sections = list(dict.fromkeys(sections))
    entry_record = next(item for item in files if item["path"] == entry_relative)
    return {
        "contract": CONTRACT,
        "status": "review_only",
        "inspection_complete": not issues,
        "pdk_id": normalized_id,
        "root": str(selected_root),
        "entry": entry_relative,
        "entry_sha256": entry_record["sha256"],
        "sections": unique_sections,
        "section_declarations": section_declarations,
        "files": files,
        "dependencies": dependencies,
        "subcircuits": subcircuits,
        "duplicate_subcircuits": duplicates,
        "licenses": licenses,
        "issues": issues,
        "limits": {"max_files": MAX_FILES, "max_file_bytes": MAX_FILE_BYTES, "max_total_bytes": MAX_TOTAL_BYTES,
                   "files_read": len(visited), "bytes_read": total_bytes},
        "model_readiness": "review_only",
        "qualified": False,
        "claims": {
            "model_execution": "unsupported",
            "native_compatibility": "not_qualified",
            "tcad": "unsupported",
            "license_interpretation": "not_performed",
        },
    }


__all__ = [
    "CONTRACT", "MAX_FILES", "MAX_FILE_BYTES", "MAX_TOTAL_BYTES",
    "PdkInventoryError", "catalog", "inspect",
]
