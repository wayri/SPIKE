"""Private, bounded persistence for local solver registrations and tuning."""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

from .openems_case_integrity import load_strict_json


SOLVER_STATE_CONTRACT = "spike/solver-manager-state/v1"
MAX_SOLVER_STATE_BYTES = 1024 * 1024
REGISTERABLE_ENGINES = {
    "external.openems",
    "external.sparselizard",
    "external.elmer",
    "external.fasthenry",
    "external.fastcap",
    "external.openfoam",
    "external.flotherm",
    "external.ngspice",
}

TUNING_SCHEMAS: Dict[str, Dict[str, Dict[str, Any]]] = {
    "native.sparse": {
        "assembly_backend": {"type": "enum", "values": ["auto", "numpy", "numba"], "default": "auto"},
        "linear_backend": {"type": "enum", "values": ["auto", "superlu", "mumps"], "default": "auto"},
        "thread_count": {"type": "integer", "minimum": 1, "maximum": 256, "default": 1},
        "direct_solver_threshold": {"type": "integer", "minimum": 100, "maximum": 10_000_000, "default": 5000},
    },
    "external.openems": {
        "mesh_resolution_mm": {"type": "number", "minimum": 0.01, "maximum": 10.0, "default": 0.5},
        "boundary_padding_cells": {"type": "integer", "minimum": 2, "maximum": 40, "default": 8},
        "end_criteria": {"type": "number", "minimum": 1e-8, "maximum": 1e-2, "default": 1e-5},
        "thread_count": {"type": "integer", "minimum": 1, "maximum": 256, "default": 1},
        "max_solver_time_s": {"type": "integer", "minimum": 10, "maximum": 604800, "default": 3600},
    },
    "external.sparselizard": {
        "polynomial_order": {"type": "integer", "minimum": 1, "maximum": 8, "default": 2},
        "adaptive_refinement": {"type": "boolean", "default": True},
        "relative_tolerance": {"type": "number", "minimum": 1e-12, "maximum": 1e-2, "default": 1e-6},
        "max_iterations": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 500},
        "thread_count": {"type": "integer", "minimum": 1, "maximum": 256, "default": 1},
        "linear_solver": {"type": "enum", "values": ["auto", "petsc", "mumps"], "default": "auto"},
    },
    "external.openfoam": {
        "parallel_ranks": {"type": "integer", "minimum": 1, "maximum": 256, "default": 1},
        "max_iterations": {"type": "integer", "minimum": 10, "maximum": 1_000_000, "default": 2000},
        "residual_target": {"type": "number", "minimum": 1e-12, "maximum": 1e-2, "default": 1e-6},
    },
}


def _state_root() -> Path:
    configured = os.environ.get("SPIKE_STATE_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "SPIKE" / "state"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SPIKE" / "state"
    xdg = os.environ.get("XDG_STATE_HOME", "").strip()
    return (Path(xdg).expanduser() if xdg else Path.home() / ".local" / "state") / "spike"


def _state_path() -> Path:
    return _state_root() / "solver-manager.json"


def _empty_state() -> Dict[str, Any]:
    return {"contract": SOLVER_STATE_CONTRACT, "registrations": {}, "tuning": {}}


def load_solver_state() -> Dict[str, Any]:
    path = _state_path()
    try:
        if not path.exists():
            return _empty_state()
        value = load_strict_json(path, max_bytes=MAX_SOLVER_STATE_BYTES)
    except (OSError, json.JSONDecodeError, ValueError):
        return _empty_state()
    if not isinstance(value, dict) or value.get("contract") != SOLVER_STATE_CONTRACT:
        raise ValueError("The solver-manager state contract is invalid.")
    registrations = value.get("registrations", {})
    tuning = value.get("tuning", {})
    if not isinstance(registrations, dict) or not isinstance(tuning, dict):
        raise ValueError("The solver-manager state structure is invalid.")
    return {"contract": SOLVER_STATE_CONTRACT, "registrations": registrations, "tuning": tuning}


def _atomic_write(state: Dict[str, Any]) -> None:
    root = _state_root()
    root.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(state, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(payload) > MAX_SOLVER_STATE_BYTES:
        raise ValueError("The solver-manager state exceeds its storage limit.")
    descriptor, temporary = tempfile.mkstemp(prefix="solver-manager-", suffix=".tmp", dir=root)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, _state_path())
        try:
            os.chmod(_state_path(), 0o600)
        except OSError:
            pass
    finally:
        try:
            Path(temporary).unlink(missing_ok=True)
        except OSError:
            pass


def registered_solver_path(engine_id: str) -> str:
    try:
        value = load_solver_state()["registrations"].get(engine_id, {})
    except (OSError, ValueError, json.JSONDecodeError):
        # Discovery is read-only and must remain available when optional local
        # state is unreadable. Mutating commands still surface the storage
        # failure instead of silently overwriting a damaged state file.
        return ""
    return str(value.get("path", "")) if isinstance(value, dict) else ""


def register_solver_path(engine_id: str, path: str) -> Dict[str, Any]:
    if engine_id not in REGISTERABLE_ENGINES:
        raise ValueError(f"Unknown registerable solver: {engine_id}")
    candidate = Path(path).expanduser().resolve(strict=True)
    if not candidate.is_dir() and not candidate.is_file():
        raise ValueError("The solver path must identify a local file or directory.")
    state = load_solver_state()
    state["registrations"][engine_id] = {"path": str(candidate), "managed": False}
    _atomic_write(state)
    return state["registrations"][engine_id]


def forget_solver_registration(engine_id: str) -> bool:
    state = load_solver_state()
    removed = state["registrations"].pop(engine_id, None) is not None
    if removed:
        _atomic_write(state)
    return removed


def _validated_tuning_value(definition: Dict[str, Any], value: Any) -> Any:
    kind = definition["type"]
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ValueError("Expected a boolean tuning value.")
        return value
    if kind == "enum":
        if value not in definition["values"]:
            raise ValueError(f"Expected one of: {', '.join(definition['values'])}")
        return value
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Expected an integer tuning value.")
        number: int | float = value
    elif kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Expected a numeric tuning value.")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Tuning values must be finite.")
    else:
        raise ValueError("Unknown tuning schema type.")
    if number < definition["minimum"] or number > definition["maximum"]:
        raise ValueError(f"Value must be between {definition['minimum']} and {definition['maximum']}.")
    return number


def update_solver_tuning(target_id: str, values: Dict[str, Any]) -> Dict[str, Any]:
    schema = TUNING_SCHEMAS.get(target_id)
    if schema is None:
        raise ValueError(f"Unknown tunable solver: {target_id}")
    if not isinstance(values, dict) or not values:
        raise ValueError("At least one tuning value is required.")
    unknown = sorted(set(values) - set(schema))
    if unknown:
        raise ValueError(f"Unknown tuning keys for {target_id}: {', '.join(unknown)}")
    state = load_solver_state()
    current = dict(state["tuning"].get(target_id, {}))
    for key, value in values.items():
        current[key] = _validated_tuning_value(schema[key], value)
    state["tuning"][target_id] = current
    _atomic_write(state)
    return current


def tuning_catalog() -> list[Dict[str, Any]]:
    state = load_solver_state()
    profiles = []
    for target_id, schema in TUNING_SCHEMAS.items():
        configured = state["tuning"].get(target_id, {})
        parameters = []
        for key, definition in schema.items():
            parameters.append({"key": key, **definition, "value": configured.get(key, definition["default"])})
        profiles.append({
            "target_id": target_id,
            "parameters": parameters,
            "application_state": "wired" if target_id == "native.sparse" else "adapter_gated",
            "note": (
                "Applied by the native sparse DC backend policy."
                if target_id == "native.sparse"
                else "Values are persisted but cannot affect execution until this external adapter consumes them."
            ),
        })
    return profiles
