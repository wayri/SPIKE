# SPDX-License-Identifier: Apache-2.0
"""Portable discovery of separately installed RF engine interpreters."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Mapping


_ENGINE_ENVIRONMENT = {
    "emerge": "SPIKE_EMERGE_PYTHON",
    "optycal": "SPIKE_OPTYCAL_PYTHON",
}
_ENGINE_ENVIRONMENTS = {
    "emerge": (".venv-emerge3", ".venv-rf", ".venv-emerge"),
    "optycal": (".venv-optycal", ".venv-rf", ".venv-emerge3"),
}


def virtual_environment_interpreters(
    environment: Path, *, platform_name: str | None = None,
) -> tuple[Path, ...]:
    """Return native interpreter paths for a virtual environment in priority order."""

    platform_name = platform_name or sys.platform
    if platform_name == "win32":
        return (environment / "Scripts" / "python.exe",)
    return (environment / "bin" / "python3", environment / "bin" / "python")


def engine_interpreter_candidates(
    engine: str,
    project_root: Path,
    explicit: str | os.PathLike[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    current_executable: str | os.PathLike[str] | None = None,
    frozen: bool | None = None,
) -> tuple[Path, ...]:
    """Resolve ordered engine candidates without launching or installing anything.

    An explicit selection is exclusive. Otherwise the engine-specific environment
    variable wins, followed by project-local virtual environments and the source
    worker interpreter. Frozen worker executables are never treated as Python.
    """

    if engine not in _ENGINE_ENVIRONMENT:
        raise ValueError(f"Unknown RF engine: {engine}")
    if explicit:
        return (Path(explicit).expanduser().resolve(),)

    environ = os.environ if environ is None else environ
    paths: list[Path] = []
    configured = environ.get(_ENGINE_ENVIRONMENT[engine])
    if configured:
        paths.append(Path(configured).expanduser().resolve())
    root = project_root.resolve()
    for name in _ENGINE_ENVIRONMENTS[engine]:
        paths.extend(
            virtual_environment_interpreters(
                root / name, platform_name=platform_name,
            )
        )
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    selected_current = sys.executable if current_executable is None else current_executable
    if selected_current and not is_frozen:
        paths.append(Path(selected_current).expanduser().resolve())

    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = os.path.normcase(os.path.abspath(path))
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return tuple(unique)


def existing_engine_interpreter(
    engine: str,
    project_root: Path,
    explicit: str | os.PathLike[str] | None = None,
    **options,
) -> Path:
    """Return the first existing candidate, retaining a useful missing path."""

    candidates = engine_interpreter_candidates(
        engine, project_root, explicit, **options,
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if candidates:
        return candidates[0]
    raise ValueError(f"No {engine} Python interpreter candidate is configured.")


__all__ = [
    "engine_interpreter_candidates",
    "existing_engine_interpreter",
    "virtual_environment_interpreters",
]
