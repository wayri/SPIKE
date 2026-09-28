"""Resolve optional solver runtimes without importing solver adapters."""

from __future__ import annotations

import os
from pathlib import Path


def app_root() -> Path:
    configured = os.environ.get("SPIKE_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def registered_engine_path(engine_id: str) -> str:
    try:
        from .solver_state import registered_solver_path

        return registered_solver_path(engine_id).strip()
    except (OSError, TypeError, ValueError):
        return ""


def openems_install_root() -> str:
    from extensions.openems_suite.runtime import openems_install_root as resolve

    return resolve()


def openems_python() -> str:
    from extensions.openems_suite.runtime import openems_python as resolve

    return resolve()


__all__ = ["app_root", "openems_install_root", "openems_python", "registered_engine_path"]
