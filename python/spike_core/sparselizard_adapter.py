"""Bounded process adapter for a separately built sparseLizard bridge.

This module deliberately does not import sparseLizard.  The upstream library is
GPL-licensed and has a C++ API; SPIKE exchanges only versioned JSON files with a
separately built ``spike-sparselizard-adapter`` executable.  A discovered
library, source tree, or arbitrary executable is never a runnable adapter.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue
from .external_pi_result_validation import validate_external_pi_multiport
from .hybrid_mesh import build_hybrid_mesh
from .openems_case_integrity import load_strict_json
from .solver_geometry import build_dc_fem_geometry, build_solver_geometry
from .solver_state import registered_solver_path
from .sparselizard_process import SparseLizardAdapterError, run_adapter_process as _run_adapter_process


SPARSELIZARD_CASE_CONTRACT = "spike/sparselizard-case/v1"
SPARSELIZARD_ADAPTER_CONTRACT = "spike/sparselizard-adapter/v1"
SPARSELIZARD_ENGINE_ID = "external.sparselizard"
PI_RESULT_CONTRACT = "spike/pi-multiport-result/v1"
PCB_RESULT_CONTRACT = "spike/sparselizard-pcb-result/v1"
ADAPTER_NAMES = ("spike-sparselizard-adapter", "spike-sparselizard-adapter.exe")
MAX_CASE_BYTES = 64 * 1024**2
DEFAULT_TIMEOUT_S = 3600
DEFAULT_MEMORY_LIMIT_MB = 4096
DEFAULT_OUTPUT_LIMIT_BYTES = 64 * 1024**2
DEFAULT_STREAM_LIMIT_BYTES = 4 * 1024**2


@dataclass(frozen=True)
class AdapterDiscovery:
    """The only trusted sources for a runnable local adapter executable."""

    available: bool
    executable: str = ""
    source: str = ""
    reason: str = ""


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SparseLizardAdapterError("Case data must contain finite JSON-compatible values.") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    encoded = _canonical_json(payload)
    if len(encoded) > MAX_CASE_BYTES:
        raise SparseLizardAdapterError(
            f"Prepared sparseLizard input exceeds the {MAX_CASE_BYTES // 1024**2}-MiB case limit."
        )
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)


def _adapter_path(candidate: str | Path | None) -> Path | None:
    if not candidate:
        return None
    try:
        path = Path(candidate).expanduser().resolve(strict=True)
    except OSError:
        return None
    if path.is_dir():
        path = next(
            (
                child
                for name in ADAPTER_NAMES
                for child in (path / name, path / "bin" / name)
                if child.is_file()
            ),
            path,
        )
    if not path.is_file() or path.name.lower() not in {name.lower() for name in ADAPTER_NAMES}:
        return None
    if os.name != "nt" and not os.access(path, os.X_OK):
        return None
    return path


def discover_sparselizard_adapter(*, executable: str | Path | None = None) -> AdapterDiscovery:
    """Find only an exact registered or PATH-named SPIKE adapter executable.

    This function intentionally ignores upstream sparseLizard libraries, source
    trees, environment roots, and arbitrary executable names.  Registration is
    local-only and never downloads, builds, or modifies an external tool.
    """

    explicit = _adapter_path(executable)
    if executable is not None:
        return (
            AdapterDiscovery(True, str(explicit), "explicit")
            if explicit else
            AdapterDiscovery(False, reason="The explicit adapter path is missing, non-executable, or not named spike-sparselizard-adapter.")
        )
    try:
        registered = _adapter_path(registered_solver_path(SPARSELIZARD_ENGINE_ID))
    except (OSError, ValueError):
        registered = None
    if registered:
        return AdapterDiscovery(True, str(registered), "registered")
    for name in ADAPTER_NAMES:
        named = shutil.which(name)
        path = _adapter_path(named)
        if path:
            return AdapterDiscovery(True, str(path), "path")
    return AdapterDiscovery(
        False,
        reason="No registered or PATH-named spike-sparselizard-adapter executable is available. No library loading, download, or installation was attempted.",
    )


def _finite(value: Any, label: str, *, positive: bool = False) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise SparseLizardAdapterError(f"{label} must be numeric.") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise SparseLizardAdapterError(f"{label} must be finite{' and positive' if positive else ''}.")
    return number


def _frequency_grid(spec: AnalysisSpec) -> List[float]:
    start = _finite(spec.frequency_start_hz, "frequency_start_hz", positive=True)
    stop = _finite(spec.frequency_stop_hz, "frequency_stop_hz", positive=True)
    points = spec.frequency_points
    if isinstance(points, bool) or not isinstance(points, int) or not 2 <= points <= 100_000:
        raise SparseLizardAdapterError("frequency_points must be an integer between 2 and 100000.")
    if stop <= start:
        raise SparseLizardAdapterError("frequency_stop_hz must be greater than frequency_start_hz for a multiport sweep.")
    ratio = (stop / start) ** (1.0 / (points - 1))
    return [start * ratio**index for index in range(points)]


def _object_index(design: DesignIR) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for object_type, collection in (
        ("trace", design.tracks), ("via", design.vias), ("pad", design.pads),
        ("zone", design.zones), ("connector_pin", design.connectors),
    ):
        for item in collection:
            if not isinstance(item, dict):
                continue
            identifier = str(item.get("id", "")).strip()
            if identifier:
                indexed[identifier] = {"object_type": object_type, "object": item}
    return indexed


def _terminal(
    raw: Any,
    *,
    label: str,
    objects: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise SparseLizardAdapterError(f"{label} must be an explicit terminal object.")
    object_id = str(raw.get("object_id", "")).strip()
    net = str(raw.get("net", "")).strip()
    object_type = str(raw.get("object_type", "")).strip()
    if not object_id or not net or not object_type:
        raise SparseLizardAdapterError(f"{label} requires object_id, object_type, and net.")
    known = objects.get(object_id)
    if known is None:
        raise SparseLizardAdapterError(f"{label} references unknown DesignIR object {object_id!r}.")
    if known["object_type"] != object_type:
        raise SparseLizardAdapterError(f"{label} object type does not match DesignIR.")
    known_net = str(known["object"].get("net_name") or known["object"].get("net") or "").strip()
    if known_net and known_net != net:
        raise SparseLizardAdapterError(f"{label} net does not match DesignIR.")
    normalized = {"object_id": object_id, "object_type": object_type, "net": net}
    if isinstance(raw.get("layers"), list):
        normalized["layers"] = [str(layer) for layer in raw["layers"] if str(layer)]
    return normalized


def _reviewed_ports(raw_ports: Any, design: DesignIR) -> List[Dict[str, Any]]:
    if not isinstance(raw_ports, list) or not 2 <= len(raw_ports) <= 64:
        raise SparseLizardAdapterError("SparseLizard PI cases require 2 through 64 reviewed differential ports.")
    objects = _object_index(design)
    ports: List[Dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, raw in enumerate(raw_ports):
        if not isinstance(raw, dict):
            raise SparseLizardAdapterError("Every sparseLizard port must be an object.")
        identifier = str(raw.get("id", "")).strip()
        role = str(raw.get("role", "")).strip()
        if not identifier or identifier in identifiers:
            raise SparseLizardAdapterError("SparseLizard port IDs must be unique and non-empty.")
        expected_role = "observation" if index == 0 else "candidate"
        if role != expected_role:
            raise SparseLizardAdapterError(f"Port {identifier} must have role {expected_role!r}.")
        if raw.get("endpoint_reviewed") is not True:
            raise SparseLizardAdapterError(f"Port {identifier} is blocked until its differential terminals are explicitly reviewed.")
        positive = _terminal(raw.get("positive_terminal"), label=f"port {identifier} positive_terminal", objects=objects)
        negative = _terminal(raw.get("negative_terminal"), label=f"port {identifier} negative_terminal", objects=objects)
        if positive["object_id"] == negative["object_id"]:
            raise SparseLizardAdapterError(f"Port {identifier} must use two distinct differential terminals.")
        identifiers.add(identifier)
        ports.append({
            "id": identifier,
            "role": role,
            "endpoint_reviewed": True,
            "positive_terminal": positive,
            "negative_terminal": negative,
            "location": raw.get("location", {}) if isinstance(raw.get("location", {}), dict) else {},
        })
    return ports


def _analysis_kind(spec: AnalysisSpec) -> str:
    mode = str(spec.mode).strip().lower()
    if mode in {"dc", "bulk_dc", "dc_ir_drop"}:
        return "dc_conduction"
    if mode in {"ac", "ac_impedance", "broadband_hf", "rlcg"}:
        return "ac_rlcg"
    if mode in {"thermal", "thermal_steady", "thermal_transient"}:
        return "thermal"
    if mode in {"field", "emi", "emi_emc", "fullwave"}:
        return "field"
    raise SparseLizardAdapterError(f"SparseLizard does not define a PCB translation for analysis mode {spec.mode!r}.")


def _mesh_payload(design: DesignIR, spec: AnalysisSpec) -> Dict[str, Any]:
    if _analysis_kind(spec) == "dc_conduction":
        try:
            return build_dc_fem_geometry(design, spec)
        except ValueError as exc:
            raise SparseLizardAdapterError(str(exc)) from exc
    mesh = build_hybrid_mesh(design, spec)
    if mesh.truncated:
        raise SparseLizardAdapterError(
            "The sparseLizard handoff mesh was truncated; raise the configured resource limit or reduce the selected geometry."
        )
    blocking = [issue for issue in mesh.issues if issue.severity == "error"]
    if blocking:
        raise SparseLizardAdapterError(
            "The sparseLizard handoff mesh is invalid: " + "; ".join(issue.message for issue in blocking[:5])
        )
    return {
        "contract": "spike/sparselizard-mesh/v1",
        "units": "mm",
        "nodes": [
            {
                "id": node.id, "point_mm": [node.x_mm, node.y_mm, node.z_mm],
                "layer": node.layer, "net": node.net,
            }
            for node in mesh.nodes
        ],
        "branches": [
            {
                "id": branch.id, "kind": branch.kind, "node_p": branch.node_p,
                "node_n": branch.node_n, "start_mm": list(branch.start_mm),
                "end_mm": list(branch.end_mm), "width_mm": branch.width_mm,
                "thickness_mm": branch.thickness_mm,
                "conductivity_s_m": branch.conductivity_s_m, "layer": branch.layer,
                "net": branch.net, "source_id": branch.source_id,
            }
            for branch in mesh.branches
        ],
        "cells": mesh.cells,
        "quality": {
            "target_size_mm": mesh.target_size_mm,
            "minimum_local_target_mm": mesh.minimum_local_target_mm,
            "feature_refined_track_count": mesh.feature_refined_track_count,
            "geometry_counts": mesh.geometry_counts,
            "issues": [issue.__dict__ for issue in mesh.issues],
        },
    }


def _materials_payload(design: DesignIR) -> List[Dict[str, Any]]:
    materials: List[Dict[str, Any]] = []
    for index, raw in enumerate(design.stackup or design.layers):
        if not isinstance(raw, dict):
            continue
        layer_type = str(raw.get("type", "")).lower()
        entry: Dict[str, Any] = {
            "id": str(raw.get("id") or raw.get("name") or f"layer-{index + 1}"),
            "name": str(raw.get("name") or raw.get("layer") or f"Layer {index + 1}"),
            "type": layer_type or "unspecified",
        }
        for source, target in (
            ("thickness", "thickness_mm"), ("thickness_mm", "thickness_mm"),
            ("epsilon_r", "relative_permittivity"), ("er", "relative_permittivity"),
            ("loss_tangent", "loss_tangent"), ("conductivity_s_m", "conductivity_s_m"),
            ("thermal_conductivity_w_mk", "thermal_conductivity_w_mk"),
            ("specific_heat_j_kgk", "specific_heat_j_kgk"),
            ("density_kg_m3", "density_kg_m3"),
        ):
            if source in raw and raw[source] not in (None, ""):
                entry[target] = _finite(raw[source], f"stackup[{index}].{source}", positive=True)
        if "copper" in layer_type or entry["name"].endswith(".Cu"):
            entry.setdefault("conductivity_s_m", 5.8e7)
        materials.append(entry)
    return materials


def _terminal_payload(spec: AnalysisSpec) -> Dict[str, Any]:
    def normalize(items: Sequence[Dict[str, Any]], role: str) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for index, raw in enumerate(items):
            if not isinstance(raw, dict):
                raise SparseLizardAdapterError(f"{role} terminal {index + 1} must be an object.")
            item = dict(raw)
            item.setdefault("id", f"{role}-{index + 1}")
            item["role"] = role
            normalized.append(item)
        return normalized

    return {
        "sources": normalize(spec.sources, "source"),
        "loads": normalize(spec.loads, "load"),
        "return_path": dict(spec.return_path),
        "probes": [dict(probe) for probe in spec.probes if isinstance(probe, dict)],
    }


def prepare_sparselizard_case(
    design: DesignIR,
    spec: AnalysisSpec,
    destination: str | Path,
    *,
    solver_geometry: Dict[str, Any] | None = None,
    ports: Sequence[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Write a deterministic PCB FEM case without executing external software."""

    geometry = solver_geometry if solver_geometry is not None else build_solver_geometry(design, spec)
    if not isinstance(geometry, dict) or geometry.get("contract") != "spike/solver-geometry/v1":
        raise SparseLizardAdapterError("SparseLizard requires spike/solver-geometry/v1 geometry.")
    kind = _analysis_kind(spec)
    raw_ports = list(ports) if ports is not None else geometry.get("excitations", {}).get("ports", [])
    reviewed = _reviewed_ports(raw_ports, design) if raw_ports else []
    if kind == "ac_rlcg" and not reviewed and not (spec.sources and spec.loads):
        raise SparseLizardAdapterError("AC/RLCG cases require reviewed ports or explicit source/load terminals.")
    frequencies = _frequency_grid(spec) if kind in {"ac_rlcg", "field"} else []
    mesh = _mesh_payload(design, spec)
    materials = _materials_payload(design)
    terminals = _terminal_payload(spec)
    root = Path(destination).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise SparseLizardAdapterError("The sparseLizard case directory must be empty.")
    root.mkdir(parents=True, exist_ok=True)
    geometry_path = root / "geometry.json"
    mesh_path = root / "mesh.json"
    _write_json(geometry_path, geometry)
    _write_json(mesh_path, mesh)
    geometry_digest = _digest(geometry)
    mesh_digest = _digest(mesh)
    request = {
        "contract": SPARSELIZARD_CASE_CONTRACT,
        "adapter_contract": SPARSELIZARD_ADAPTER_CONTRACT,
        "engine_id": SPARSELIZARD_ENGINE_ID,
        "analysis": {
            "analysis_id": str(spec.analysis_id),
            "mode": str(spec.mode),
            "net_names": [str(net) for net in spec.net_names if str(net)],
            "required_capabilities": [str(item) for item in spec.required_capabilities if str(item)],
            "physics": kind,
            "formulation": str(spec.formulation),
        },
        "design": {"design_id": str(design.design_id), "name": str(design.name)},
        "geometry": {"path": "geometry.json", "sha256": geometry_digest},
        "mesh": {"path": "mesh.json", "sha256": mesh_digest},
        "materials": materials,
        "terminals": terminals,
        "ports": reviewed,
        "frequencies_hz": frequencies,
        "output": {
            "contract": PI_RESULT_CONTRACT if reviewed and kind == "ac_rlcg" else PCB_RESULT_CONTRACT,
            "path": "result.json",
        },
    }
    request_digest = _digest(request)
    case = {**request, "provenance": {
        "geometry_digest": geometry_digest, "mesh_digest": mesh_digest,
        "request_digest": request_digest,
    }}
    _write_json(root / "case.json", case)
    return {
        "contract": SPARSELIZARD_CASE_CONTRACT,
        "status": "prepared_review_required",
        "case_directory": str(root),
        "case_path": str(root / "case.json"),
        "geometry_path": str(geometry_path),
        "mesh_path": str(mesh_path),
        "geometry_digest": geometry_digest,
        "mesh_digest": mesh_digest,
        "request_digest": request_digest,
        "ports": reviewed,
        "frequencies_hz": frequencies,
        "physics": kind,
        "mesh_counts": {
            "nodes": len(mesh.get("nodes", [])),
            "branches": len(mesh.get("branches", [])),
            "cells": len(mesh.get("cells", mesh.get("volumes", []))),
            "terminal_boundary_faces": len(mesh.get("terminal_boundary_faces", [])),
        },
        "model_status": "unvalidated",
        "message": "Case prepared. A separately built adapter may run it only after local executable discovery; imported results are independently validated.",
    }


def _case_path(root: Path, relative: str, label: str) -> Path:
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise SparseLizardAdapterError(f"SparseLizard {label} is missing or outside the case directory.")
    return path


def _bounded_resource(value: Any, label: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise SparseLizardAdapterError(f"{label} must be an integer between {minimum} and {maximum}.")
    return value


def _finite_sample(value: Any, label: str) -> float:
    return _finite(value, label)


def _normalize_sample(raw: Any, label: str, *, vector: bool = False) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise SparseLizardAdapterError(f"{label} must be an object.")
    point = raw.get("point_mm")
    if point is None:
        point = [raw.get("x_mm"), raw.get("y_mm"), raw.get("z_mm", 0.0)]
    if not isinstance(point, (list, tuple)) or len(point) != 3:
        raise SparseLizardAdapterError(f"{label}.point_mm must contain three coordinates.")
    normalized = {
        "x_mm": _finite_sample(point[0], f"{label}.x_mm"),
        "y_mm": _finite_sample(point[1], f"{label}.y_mm"),
        "z_mm": _finite_sample(point[2], f"{label}.z_mm"),
    }
    for key in ("layer", "net", "element_id", "object_id"):
        if raw.get(key) not in (None, ""):
            normalized[key] = str(raw[key])
    if vector:
        components = raw.get("value")
        if components is None:
            components = [raw.get("dx"), raw.get("dy"), raw.get("dz", 0.0)]
        if not isinstance(components, (list, tuple)) or len(components) != 3:
            raise SparseLizardAdapterError(f"{label}.value must contain three vector components.")
        normalized.update({
            "dx": _finite_sample(components[0], f"{label}.dx"),
            "dy": _finite_sample(components[1], f"{label}.dy"),
            "dz": _finite_sample(components[2], f"{label}.dz"),
        })
        normalized["value"] = math.sqrt(normalized["dx"] ** 2 + normalized["dy"] ** 2 + normalized["dz"] ** 2)
    else:
        normalized["value"] = _finite_sample(raw.get("value"), f"{label}.value")
    return normalized


def _validate_pcb_result(payload: Dict[str, Any], case: Dict[str, Any]) -> Dict[str, Any]:
    if payload.get("contract") != PCB_RESULT_CONTRACT:
        raise SparseLizardAdapterError(f"Expected {PCB_RESULT_CONTRACT}.")
    if payload.get("engine_id") != SPARSELIZARD_ENGINE_ID or payload.get("status") != "completed":
        raise SparseLizardAdapterError("SparseLizard PCB output requires the expected engine_id and completed status.")
    model_status = str(payload.get("model_status", "")).lower()
    if model_status not in {"experimental", "reference_validated", "validated"}:
        raise SparseLizardAdapterError("SparseLizard PCB output is unvalidated or otherwise unusable.")
    convergence = payload.get("convergence")
    if not isinstance(convergence, dict) or convergence.get("passed") is not True:
        raise SparseLizardAdapterError("SparseLizard PCB output requires passed mesh convergence.")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict) or not provenance.get("solver_version") or not provenance.get("adapter_version"):
        raise SparseLizardAdapterError("SparseLizard PCB output requires solver and adapter provenance.")
    if model_status in {"reference_validated", "validated"} and not provenance.get("validation_evidence"):
        raise SparseLizardAdapterError("Validated sparseLizard PCB output requires validation_evidence.")
    expected = case.get("provenance", {})
    for key in ("geometry_digest", "mesh_digest", "request_digest"):
        if provenance.get(key) != expected.get(key):
            raise SparseLizardAdapterError(f"SparseLizard PCB output {key} does not match the prepared case.")
    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, dict):
        raise SparseLizardAdapterError("SparseLizard PCB output requires fields.")
    scalar_fields: Dict[str, Any] = {}
    for name, field in raw_fields.get("scalar_fields", {}).items():
        if not isinstance(field, dict) or not isinstance(field.get("samples"), list):
            raise SparseLizardAdapterError(f"Scalar field {name!r} requires samples.")
        scalar_fields[str(name)] = [
            _normalize_sample(sample, f"scalar_fields.{name}[{index}]")
            for index, sample in enumerate(field["samples"])
        ]
    vector_fields: Dict[str, Any] = {}
    for name, field in raw_fields.get("vector_fields", {}).items():
        if not isinstance(field, dict) or not isinstance(field.get("samples"), list):
            raise SparseLizardAdapterError(f"Vector field {name!r} requires samples.")
        vector_fields[str(name)] = [
            _normalize_sample(sample, f"vector_fields.{name}[{index}]", vector=True)
            for index, sample in enumerate(field["samples"])
        ]
    mesh = payload.get("mesh", [])
    if not isinstance(mesh, list):
        raise SparseLizardAdapterError("SparseLizard PCB output mesh must be a list.")
    issues = [
        ValidationIssue(
            code=str(item.get("code", "SPARSELIZARD_RESULT_NOTICE")),
            severity=str(item.get("severity", "info")),
            message=str(item.get("message", "")),
            path=str(item.get("path", "")),
            suggestion=str(item.get("suggestion", "")),
            status=str(item.get("status", "open")),
        )
        for item in payload.get("issues", []) if isinstance(item, dict)
    ]
    return AnalysisResult(
        analysis_id=str(payload.get("analysis_id") or case.get("analysis", {}).get("analysis_id", "")),
        mode=str(payload.get("mode") or case.get("analysis", {}).get("mode", "")),
        status="completed", model_status=model_status,
        summary=dict(payload.get("summary", {})),
        fields={
            "visualization": {
                "schema": "spike/result-visualization/v1",
                "scalar_fields": scalar_fields,
                "vector_fields": vector_fields,
                "mesh": mesh,
            },
            "native": dict(raw_fields.get("native", {})),
        },
        networks=dict(payload.get("networks", {})),
        probes=[dict(item) for item in payload.get("probes", []) if isinstance(item, dict)],
        issues=issues,
        provenance={**provenance, "convergence": convergence, "engine_id": SPARSELIZARD_ENGINE_ID},
    ).to_dict()


def run_sparselizard_case(
    case_directory: str | Path,
    *,
    executable: str | Path | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES,
    stream_limit_bytes: int = DEFAULT_STREAM_LIMIT_BYTES,
    cancellation_event: threading.Event | None = None,
) -> Dict[str, Any]:
    """Execute and import one local sparseLizard adapter result.

    This is process-isolated orchestration, not a direct sparseLizard binding.
    The result is rejected unless it passes the common external PI validator and
    binds to the prepared geometry and request digests.
    """

    timeout = _bounded_resource(timeout_s, "timeout_s", 1, 604800)
    memory = _bounded_resource(memory_limit_mb, "memory_limit_mb", 128, 1_048_576)
    output_limit = _bounded_resource(output_limit_bytes, "output_limit_bytes", 1024, 512 * 1024**2)
    stream_limit = _bounded_resource(stream_limit_bytes, "stream_limit_bytes", 1024, 64 * 1024**2)
    root = Path(case_directory).expanduser().resolve(strict=True)
    case_path = _case_path(root, "case.json", "case file")
    case = load_strict_json(case_path, max_bytes=MAX_CASE_BYTES, label="sparseLizard case")
    if not isinstance(case, dict) or case.get("contract") != SPARSELIZARD_CASE_CONTRACT:
        raise SparseLizardAdapterError("The supplied directory does not contain a sparseLizard v1 case.")
    geometry = case.get("geometry", {})
    if not isinstance(geometry, dict):
        raise SparseLizardAdapterError("SparseLizard case geometry metadata is invalid.")
    geometry_path = _case_path(root, str(geometry.get("path", "")), "geometry file")
    geometry_payload = load_strict_json(geometry_path, max_bytes=MAX_CASE_BYTES, label="sparseLizard geometry")
    mesh_metadata = case.get("mesh", {})
    if not isinstance(mesh_metadata, dict):
        raise SparseLizardAdapterError("SparseLizard case mesh metadata is invalid.")
    mesh_path = _case_path(root, str(mesh_metadata.get("path", "")), "mesh file")
    mesh_payload = load_strict_json(mesh_path, max_bytes=MAX_CASE_BYTES, label="sparseLizard mesh")
    expected_geometry_digest = str(case.get("provenance", {}).get("geometry_digest", ""))
    expected_request_digest = str(case.get("provenance", {}).get("request_digest", ""))
    unsigned_case = dict(case)
    unsigned_case.pop("provenance", None)
    expected_mesh_digest = str(case.get("provenance", {}).get("mesh_digest", ""))
    if (_digest(geometry_payload) != expected_geometry_digest
            or _digest(mesh_payload) != expected_mesh_digest
            or _digest(unsigned_case) != expected_request_digest):
        raise SparseLizardAdapterError("The sparseLizard case changed after preparation; prepare it again.")
    discovery = discover_sparselizard_adapter(executable=executable)
    if not discovery.available:
        raise SparseLizardAdapterError(discovery.reason)
    output = root / "result.json"
    if output.exists():
        raise SparseLizardAdapterError("The sparseLizard case already has a result.json; use a fresh case directory to prevent stale-result import.")
    run = _run_adapter_process(
        [discovery.executable, "run", "--case", str(case_path), "--output", str(output)],
        cwd=root,
        timeout_s=timeout,
        memory_limit_mb=memory,
        output_limit_bytes=output_limit,
        stream_limit_bytes=stream_limit,
        cancellation_event=cancellation_event,
    )
    if run["return_code"] != 0:
        diagnostic = run["stderr"].strip() or run["stdout"].strip() or f"exit code {run['return_code']}"
        raise SparseLizardAdapterError(f"SparseLizard adapter failed: {diagnostic[:2048]}")
    if not output.is_file() or output.is_symlink() or output.stat().st_size > output_limit:
        raise SparseLizardAdapterError("SparseLizard adapter did not produce a bounded regular result.json file.")
    payload = load_strict_json(output, max_bytes=output_limit, label="sparseLizard result")
    if not isinstance(payload, dict):
        raise SparseLizardAdapterError("SparseLizard result must be a JSON object.")
    try:
        if payload.get("contract") == PI_RESULT_CONTRACT:
            normalized = validate_external_pi_multiport(
                payload,
                expected_engine_id=SPARSELIZARD_ENGINE_ID,
                expected_frequencies_hz=case.get("frequencies_hz", []),
            )
        else:
            normalized = _validate_pcb_result(payload, case)
    except ValueError as exc:
        raise SparseLizardAdapterError(f"SparseLizard result failed external PI validation: {exc}") from exc
    provenance = normalized.get("provenance", {})
    if provenance.get("geometry_digest") != expected_geometry_digest:
        raise SparseLizardAdapterError("SparseLizard result geometry_digest does not match the prepared case.")
    if provenance.get("request_digest") != expected_request_digest:
        raise SparseLizardAdapterError("SparseLizard result request_digest does not match the prepared case.")
    return {
        "contract": "spike/sparselizard-run/v1",
        "status": "completed",
        "model_status": normalized["model_status"],
        "adapter": {"executable": discovery.executable, "source": discovery.source},
        "execution": {
            "timeout_s": timeout,
            "memory_limit_mb": memory,
            "memory_limit_enforced": run["memory_limit_enforced"],
            "output_limit_bytes": output_limit,
        },
        "result": normalized,
    }
