"""Standalone external-engine locations without SPIKE application state."""

from __future__ import annotations

import os
from pathlib import Path


def app_root() -> Path:
    configured = os.environ.get("SPIKES_HOME", "").strip()
    return Path(configured).expanduser().resolve() if configured else Path(__file__).resolve().parents[2]


def registered_engine_path(engine_id: str) -> str:
    names = {
        "external.ngspice": "SPIKES_NGSPICE",
    }
    value = os.environ.get(names.get(engine_id, ""), "").strip() if engine_id in names else ""
    return str(Path(value).expanduser().resolve()) if value else ""


__all__ = ["app_root", "registered_engine_path"]
