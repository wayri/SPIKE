"""Bounded worker boundary for the owned SPIKES circuit engine.

The worker owns native handles and exposes opaque session identifiers.  This
keeps DLL paths and ctypes objects out of the desktop/UI protocol while still
allowing deterministic, step-at-a-time interactive simulation.
"""

from __future__ import annotations

import atexit
import hashlib
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from python.spikes.contracts import CircuitProject, ProbeDescriptor
from python.spikes.native_abi import (
    SPIKES_ABI_VERSION,
    NativeLibrary,
    NativeTransientCheckpoint,
    NativeTransientSession,
    load_native_library,
)
from python.spikes.native_runner import _nodes, _populate, run_native_project
from python.spikes.netlist import parse_netlist


ENGINE_CONTRACT = "spikes/owned-engine-status/v1"
SESSION_CONTRACT = "spikes/interactive-session/v1"
MAX_NETLIST_BYTES = 2 * 1024 * 1024
MAX_SESSIONS = 32
MAX_PROBES = 256
MAX_STEPS_PER_REQUEST = 10_000
MAX_CHECKPOINTS_PER_SESSION = 64


def _library_name() -> str:
    if sys.platform == "win32":
        return "spikes_c_api.dll"
    if sys.platform == "darwin":
        return "libspikes_c_api.dylib"
    return "libspikes_c_api.so"


def owned_library_path() -> Path:
    """Resolve only release-owned locations; never search PATH or user input."""

    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidate = Path(frozen_root) / "spikes" / _library_name()
    else:
        root = Path(__file__).resolve().parents[2]
        candidate = root / "build-spikes-hybrid" / _library_name()
    return candidate.resolve(strict=True)


_library: NativeLibrary | None = None


def _engine() -> NativeLibrary:
    global _library
    if _library is None:
        _library = load_native_library(owned_library_path())
    return _library


def engine_status() -> dict[str, Any]:
    try:
        library = _engine()
    except (OSError, RuntimeError, ValueError) as exc:
        return {
            "contract": ENGINE_CONTRACT,
            "status": "unavailable",
            "available": False,
            "error": str(exc),
            "model_status": "experimental",
            "hard_realtime_qualified": False,
            "hil_qualified": False,
        }
    library_bytes = library.path.read_bytes()
    return {
        "contract": ENGINE_CONTRACT,
        "status": "ready",
        "available": True,
        "abi_version": SPIKES_ABI_VERSION,
        "library": str(library.path),
        "library_bytes": len(library_bytes),
        "library_sha256": hashlib.sha256(library_bytes).hexdigest(),
        "features": {
            "transient": library.transient_available,
            "persistent_sessions": library.transient_session_available,
            "interactive_source_updates": library.transient_session_available,
            "checkpoints": library.transient_session_available,
            "selectable_integration": library.session_integration_method_available,
            "waveform_sources": library.waveform_sources_available,
            "sparse_linear_solvers": library.linear_solver_options_available,
        },
        "execution_class": "soft_realtime",
        "model_status": "experimental",
        "hard_realtime_qualified": False,
        "hil_qualified": False,
    }


def _netlist(params: Mapping[str, Any]) -> tuple[str, tuple[ProbeDescriptor, ...]]:
    text = params.get("netlist")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("netlist must be non-empty SPICE text")
    if len(text.encode("utf-8")) > MAX_NETLIST_BYTES:
        raise ValueError(f"netlist exceeds the {MAX_NETLIST_BYTES}-byte worker limit")
    raw_probes = params.get("probes", ())
    if not isinstance(raw_probes, (list, tuple)) or len(raw_probes) > MAX_PROBES:
        raise ValueError(f"probes must be an array with at most {MAX_PROBES} entries")
    probes = tuple(ProbeDescriptor.parse(str(item)) for item in raw_probes)
    return text, probes


def _project(params: Mapping[str, Any]) -> CircuitProject:
    text, probes = _netlist(params)
    return parse_netlist(
        text,
        source_name="<worker-request>",
        probes=probes,
        native_extensions=True,
    )


def run_netlist(params: Mapping[str, Any]) -> dict[str, Any]:
    project = _project(params)
    method = str(params.get("integration_method", "hybrid_trapezoidal"))
    return run_native_project(
        project, _engine().path, integration_method=method
    ).to_dict()


def _probe_value(probe: ProbeDescriptor, session: NativeTransientSession) -> float:
    if probe.quantity == "node_voltage":
        value = session.node_voltage(probe.targets[0])
        if len(probe.targets) == 2:
            value -= session.node_voltage(probe.targets[1])
        return value
    if probe.quantity == "element_current":
        return session.element_current(probe.targets[0])
    return session.element_power(probe.targets[0])


@dataclass
class _OwnedSession:
    native: NativeTransientSession
    project: CircuitProject
    probes: tuple[ProbeDescriptor, ...]
    nominal_step_s: float
    checkpoints: dict[str, NativeTransientCheckpoint] = field(default_factory=dict)

    def source_name(self, requested: Any) -> str:
        normalized = str(requested).upper()
        for element in self.project.elements:
            if element.name.upper() == normalized:
                return element.name
        raise ValueError(f"unknown circuit element {requested!r}")

    def sample(self) -> dict[str, Any]:
        time_s, step_index = self.native.position
        return {
            "time_s": time_s,
            "step_index": step_index,
            "values": {probe.name: _probe_value(probe, self.native) for probe in self.probes},
        }

    def close(self) -> None:
        for checkpoint in self.checkpoints.values():
            checkpoint.close()
        self.checkpoints.clear()
        self.native.close()


_sessions: dict[str, _OwnedSession] = {}


def _session(session_id: Any) -> _OwnedSession:
    try:
        return _sessions[str(session_id)]
    except KeyError as exc:
        raise ValueError("unknown or closed SPIKES interactive session") from exc


def create_session(params: Mapping[str, Any]) -> dict[str, Any]:
    if len(_sessions) >= MAX_SESSIONS:
        raise ValueError(f"worker session limit ({MAX_SESSIONS}) reached")
    project = _project(params)
    if project.analysis.mode != "transient":
        raise ValueError("interactive sessions require a .tran analysis directive")
    probes = project.probes
    if not probes:
        probes = tuple(
            ProbeDescriptor.parse(f"V({node})") for node in _nodes(project) if node != "0"
        )
    if len(probes) > MAX_PROBES:
        raise ValueError(f"interactive signal count exceeds {MAX_PROBES}")
    method = str(params.get("integration_method", "hybrid_trapezoidal"))
    initialize = params.get("initialize_from_operating_point", False)
    if not isinstance(initialize, bool):
        raise ValueError("initialize_from_operating_point must be boolean")
    library = _engine()
    with library.circuit() as circuit:
        _populate(circuit, project)
        native = circuit.transient_session(
            initialize_from_operating_point=initialize,
            integration_method=method,
        )
    assert project.analysis.time_step_s is not None
    session_id = str(uuid.uuid4())
    owned = _OwnedSession(native, project, probes, project.analysis.time_step_s)
    _sessions[session_id] = owned
    time_s, step_index = owned.native.position
    return {
        "contract": SESSION_CONTRACT,
        "status": "ready",
        "session_id": session_id,
        "execution_class": "soft_realtime",
        "nominal_step_s": owned.nominal_step_s,
        "signals": [probe.to_dict() for probe in probes],
        "position": {"time_s": time_s, "step_index": step_index},
        "has_accepted_point": False,
        "hard_realtime_qualified": False,
        "hil_qualified": False,
    }


def step_session(params: Mapping[str, Any]) -> dict[str, Any]:
    owned = _session(params.get("session_id"))
    raw_sources = params.get("source_values", {})
    if not isinstance(raw_sources, dict) or len(raw_sources) > MAX_PROBES:
        raise ValueError(f"source_values must be an object with at most {MAX_PROBES} entries")
    for element_id, value in raw_sources.items():
        owned.native.set_source_value(owned.source_name(element_id), value)
    steps = params.get("steps", 1)
    if isinstance(steps, bool) or not isinstance(steps, int) or not 1 <= steps <= MAX_STEPS_PER_REQUEST:
        raise ValueError(f"steps must be an integer from 1 to {MAX_STEPS_PER_REQUEST}")
    step_s = float(params.get("step_s", owned.nominal_step_s))
    capture = params.get("capture", "last")
    if capture not in {"last", "all"}:
        raise ValueError("capture must be 'last' or 'all'")
    samples: list[dict[str, Any]] = []
    for _ in range(steps):
        if not owned.native.step(step_s):
            raise RuntimeError(owned.native.message or "native transient step was rejected")
        if capture == "all":
            samples.append(owned.sample())
    if capture == "last":
        samples.append(owned.sample())
    return {
        "contract": SESSION_CONTRACT,
        "status": owned.native.status,
        "session_id": str(params.get("session_id")),
        "samples": samples,
        "diagnostics": owned.native.diagnostics(),
    }


def checkpoint_session(params: Mapping[str, Any]) -> dict[str, Any]:
    owned = _session(params.get("session_id"))
    if len(owned.checkpoints) >= MAX_CHECKPOINTS_PER_SESSION:
        raise ValueError(f"checkpoint limit ({MAX_CHECKPOINTS_PER_SESSION}) reached")
    checkpoint_id = str(uuid.uuid4())
    owned.checkpoints[checkpoint_id] = owned.native.checkpoint()
    return {
        "contract": SESSION_CONTRACT,
        "status": "checkpointed",
        "session_id": str(params.get("session_id")),
        "checkpoint_id": checkpoint_id,
        "sample": owned.sample(),
    }


def restore_session(params: Mapping[str, Any]) -> dict[str, Any]:
    owned = _session(params.get("session_id"))
    checkpoint_id = str(params.get("checkpoint_id", ""))
    try:
        checkpoint = owned.checkpoints[checkpoint_id]
    except KeyError as exc:
        raise ValueError("unknown checkpoint for this SPIKES session") from exc
    owned.native.restore(checkpoint)
    return {
        "contract": SESSION_CONTRACT,
        "status": "restored",
        "session_id": str(params.get("session_id")),
        "checkpoint_id": checkpoint_id,
        "sample": owned.sample(),
    }


def close_session(params: Mapping[str, Any]) -> dict[str, Any]:
    session_id = str(params.get("session_id", ""))
    owned = _session(session_id)
    owned.close()
    del _sessions[session_id]
    return {"contract": SESSION_CONTRACT, "status": "closed", "session_id": session_id}


def close_all_sessions() -> None:
    for owned in tuple(_sessions.values()):
        owned.close()
    _sessions.clear()


_WORKER_OPERATIONS = {
    "spikes_run_netlist": run_netlist,
    "spikes_session_create": create_session,
    "spikes_session_step": step_session,
    "spikes_session_checkpoint": checkpoint_session,
    "spikes_session_restore": restore_session,
    "spikes_session_close": close_session,
}


def handle_worker_method(method: Any, params: Mapping[str, Any]) -> dict[str, Any] | None:
    if method == "spikes_engine_status":
        return engine_status()
    operation = _WORKER_OPERATIONS.get(str(method))
    return None if operation is None else operation(params)


atexit.register(close_all_sessions)


__all__ = [
    "checkpoint_session",
    "close_all_sessions",
    "close_session",
    "create_session",
    "engine_status",
    "handle_worker_method",
    "owned_library_path",
    "restore_session",
    "run_netlist",
    "step_session",
]
