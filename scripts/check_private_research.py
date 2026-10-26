#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail when private native-reference research enters a publication set."""

from __future__ import annotations

import argparse
import fnmatch
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

# These patterns intentionally exclude the public extensions/optycal_suite and
# examples/optycal trees. Additions must name a private research family rather
# than use a generic *optics* exclusion.
PRIVATE_PATTERNS = (
    "src/solvers/optics/**",
    "src/solvers/particles/**",
    "src/solvers/electron_optics/**",
    "src/solvers/electron-optics/**",
    "src/solvers/reference_physics/**",
    "python/spike_core/solvers/optics/**",
    "python/spike_core/solvers/particles/**",
    "python/spike_core/solvers/electron_optics/**",
    "python/spike_core/solvers/electron-optics/**",
    "python/spike_core/solvers/reference_physics/**",
    "src/optics/**",
    "src/particles/**",
    "src/electron_optics/**",
    "src/electron-optics/**",
    "tests/test_native_optics*.cpp",
    "tests/test_native_particle*.cpp",
    "tests/test_*electron_optics*",
    "docs/validation/NATIVE_OPTICS*",
    "docs/validation/NATIVE_PARTICLE*",
    "docs/validation/*ELECTRON_OPTICS*",
    "docs/OPTICS_PHOTONICS_MATERIALS_PLAN.md",
    "docs/GENERAL_PHYSICS_AND_WAVE_OPTICS_PLAN.md",
    "docs/CHARGED_PARTICLE_VACUUM_PLAN.md",
    "docs/ELECTRON_OPTICS*",
    "docs/solvers/reference-physics/**",
    "docs/solvers/electron-optics/**",
    "python/spike_core/electron_optics*.py",
    "python/spike_core/electron_optics/**",
    "python/spike_core/electron-optics/**",
)


def normalize_path(value: str) -> str:
    path = value.strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.rstrip("/")


def private_paths(paths: set[str] | list[str]) -> list[str]:
    normalized = {normalize_path(path) for path in paths if normalize_path(path)}
    return sorted(
        path for path in normalized
        if any(fnmatch.fnmatchcase(path.casefold(), pattern.casefold()) for pattern in PRIVATE_PATTERNS)
    )


def _git_paths(repository: Path, *arguments: str, allow_missing_head: bool = False) -> set[str]:
    process = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if process.returncode != 0:
        if allow_missing_head and b"HEAD" in process.stderr:
            return set()
        raise RuntimeError(process.stderr.decode("utf-8", errors="replace").strip())
    return {
        normalize_path(item.decode("utf-8", errors="strict"))
        for item in process.stdout.split(b"\0") if item
    }


def publication_paths(repository: Path) -> set[str]:
    """Return the union of the index and HEAD publication trees.

    The index check catches ``git add -f`` immediately. Including HEAD keeps a
    committed private file blocked until the commit that removes it exists.
    Ignored, untracked local research is deliberately absent.
    """

    repository = repository.resolve()
    indexed = _git_paths(repository, "ls-files", "-z", "--cached")
    committed = _git_paths(
        repository, "ls-tree", "-rz", "--name-only", "HEAD",
        allow_missing_head=True,
    )
    return indexed | committed


def read_path_list(path: Path) -> set[str]:
    """Read a newline-delimited archive or package file listing."""

    return {
        normalize_path(line) for line in path.read_text(encoding="utf-8").splitlines()
        if normalize_path(line)
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument(
        "--paths-from", action="append", default=[], type=Path,
        help="Also inspect a newline-delimited release/archive file list.",
    )
    args = parser.parse_args(argv)
    try:
        paths = publication_paths(args.repo)
        for listing in args.paths_from:
            paths.update(read_path_list(listing))
        blocked = private_paths(paths)
    except (OSError, RuntimeError, UnicodeError) as exc:
        print(f"Private research publication gate could not inspect its inputs: {exc}", file=sys.stderr)
        return 2
    if blocked:
        print("Private native-reference research is present in the publication set:", file=sys.stderr)
        for path in blocked:
            print(f"  {path}", file=sys.stderr)
        print("Remove these paths from Git/release inputs; ignored local copies may remain.", file=sys.stderr)
        return 1
    print(f"Private research publication gate passed ({len(paths)} publication paths inspected).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
