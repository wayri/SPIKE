#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Verify the canonical solver source-layout manifest without importing solvers."""

from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "solvers" / "source-layout.json"
CONTRACT = "spike/solver-source-layout/v1"
ACTIVE_SUFFIXES = {".py", ".ts", ".tsx", ".mjs", ".spec"}
EXCLUDED_PARTS = {
    ".git", ".local", ".pytest_cache", "__pycache__", "artifacts", "build",
    "dist", "dist-release", "docs", "node_modules", "runtime", "venv", ".venv",
}
ACTIVE_ROOTS = ("python", "scripts", "tests", "extensions", "app/src", "app/scripts", "integrations")
STALE_SCAN_ALLOWLIST = {
    "scripts/verify_solver_layout.py",
    "tests/python/test_solver_layout.py",
}
COMPATIBILITY_REFERENCES = {
    # This generated standalone package intentionally supplies a legacy shim;
    # the shared application implementation has no old flat module.
    "tests/python/test_spikes_standalone_packaging.py": {
        "spike_core.native_mna", "python.spike_core.native_mna",
    },
}


class LayoutError(ValueError):
    pass


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise LayoutError(f"{field} paths must be nonempty forward-slash strings")
    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("./") or ".." in path.parts or str(path) != value:
        raise LayoutError(f"{field} path is not canonical repository-relative POSIX: {value!r}")
    return value


def load_manifest(path: Path) -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LayoutError(f"cannot read layout manifest {path}: {exc}") from exc
    if not isinstance(raw, dict) or set(raw) != {"contract", "python_modules", "native_files"}:
        raise LayoutError("layout manifest requires exactly contract, python_modules, and native_files")
    if raw["contract"] != CONTRACT:
        raise LayoutError(f"unsupported layout contract: {raw['contract']!r}")
    result: dict[str, dict[str, str]] = {}
    targets: dict[str, str] = {}
    for field in ("python_modules", "native_files"):
        mapping = raw[field]
        if not isinstance(mapping, dict) or not mapping:
            raise LayoutError(f"{field} must be a nonempty object")
        normalized: dict[str, str] = {}
        for old_raw, new_raw in mapping.items():
            old = _relative_path(old_raw, field)
            new = _relative_path(new_raw, field)
            if old == new:
                raise LayoutError(f"{field} source and destination are identical: {old}")
            if old in normalized:
                raise LayoutError(f"duplicate {field} source: {old}")
            previous = targets.get(new)
            if previous is not None:
                raise LayoutError(f"duplicate layout destination {new}: {previous} and {old}")
            targets[new] = old
            normalized[old] = new
        result[field] = normalized
    return result


def _python_package_errors(root: Path, destination: str) -> list[str]:
    path = PurePosixPath(destination)
    if path.suffix != ".py" or path.parts[:2] != ("python", "spike_core"):
        return [f"Python destination must be a .py file under python/spike_core: {destination}"]
    errors = []
    directory = (root / destination).parent
    package_root = root / "python"
    while directory.is_relative_to(package_root):
        if not (directory / "__init__.py").is_file():
            errors.append(f"missing package initializer: {(directory / '__init__.py').relative_to(root).as_posix()}")
        if directory == package_root:
            break
        directory = directory.parent
    return errors


def _active_source_files(root: Path):
    for source_name in ACTIVE_ROOTS:
        source_root = root / source_name
        if not source_root.is_dir():
            continue
        for directory, names, filenames in os.walk(source_root):
            names[:] = [name for name in names if name not in EXCLUDED_PARTS]
            for filename in filenames:
                path = Path(directory) / filename
                if path.suffix not in ACTIVE_SUFFIXES:
                    continue
                relative = path.relative_to(root).as_posix()
                if relative in STALE_SCAN_ALLOWLIST:
                    continue
                yield path, relative


def _old_module_names(mapping: dict[str, str]) -> dict[str, str]:
    result = {}
    for old in mapping:
        path = PurePosixPath(old)
        if path.suffix != ".py" or path.parts[:2] != ("python", "spike_core"):
            raise LayoutError(f"Python source must be a .py file under python/spike_core: {old}")
        result[old] = ".".join(path.with_suffix("").parts)
    return result


def stale_references(root: Path, mapping: dict[str, str]) -> list[str]:
    old_modules = _old_module_names(mapping)
    basenames = {PurePosixPath(old).stem: old for old in mapping}
    module_to_old = {module: old for old, module in old_modules.items()}
    module_to_old.update({module.removeprefix("python."): old for old, module in old_modules.items()})
    # Extract only the first package component, then use constant-time lookup.
    # Hundreds of literal alternatives with two namespace prefixes otherwise
    # retry every alternative at every nonmatching source character.
    combined = re.compile(r"(?<![A-Za-z0-9_.])(?:python\.)?spike_core\.[A-Za-z_][A-Za-z0-9_]*")
    errors = []
    for path, relative in _active_source_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"cannot scan {relative}: {exc}")
            continue
        for match in combined.finditer(text):
            if match.group(0) in COMPATIBILITY_REFERENCES.get(relative, set()):
                continue
            old = module_to_old.get(match.group(0))
            if old is None:
                continue
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"stale moved-module reference {old} in {relative}:{line}")
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError as exc:
            errors.append(f"cannot parse active Python source {relative}:{exc.lineno}: {exc.msg}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in {"python.spike_core", "spike_core"}:
                for alias in node.names:
                    old = basenames.get(alias.name)
                    if old is not None:
                        errors.append(
                            f"stale flat from-import {old} in {relative}:{node.lineno}"
                        )
    return sorted(set(errors))


def validate_layout(root: Path, manifest_path: Path) -> dict[str, Any]:
    root = root.resolve()
    mappings = load_manifest(manifest_path)
    errors = []
    for field, mapping in mappings.items():
        for old, new in mapping.items():
            if (root / old).exists():
                errors.append(f"moved source still exists: {old}")
            if not (root / new).is_file():
                errors.append(f"moved destination is missing: {new}")
            if field == "python_modules":
                errors.extend(_python_package_errors(root, new))
    errors.extend(stale_references(root, mappings["python_modules"]))
    return {
        "contract": CONTRACT,
        "status": "passed" if not errors else "failed",
        "manifest": str(manifest_path.resolve()),
        "python_modules": len(mappings["python_modules"]),
        "native_files": len(mappings["native_files"]),
        "errors": sorted(set(errors)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args(argv)
    try:
        report = validate_layout(args.root, args.manifest)
    except LayoutError as exc:
        report = {"contract": CONTRACT, "status": "failed", "errors": [str(exc)]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
