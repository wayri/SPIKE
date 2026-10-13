# SPDX-License-Identifier: Apache-2.0
"""Explicit-reference capacitance handoff, not an arbitrary-PCB field solver.

The supplied Maxwell convention is Q = C V with the named return removed.
For a passive capacitor graph, C_ij = -c_ij and C_i0 = sum_j C_ij.
Thus E = V.T C V / 2 equals sum_edges c_ab (Va - Vb)^2 / 2.
Keeping every mutual edge preserves conductor states; replacing diagonals by
ground capacitors does not. Only graph-realizable matrices are admitted here.
This independently authored algebra is not an external solver implementation.

Geometry uses the existing unique-area estimator, retaining its approximate
status. Explicit net-to-node assignment assumes each selected net equipotential;
it does not establish location-specific capacitance, fringing or field accuracy.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

import numpy as np

from .contracts import AnalysisSpec, SpiDeR
from .hybrid_mesh import MeshBranch
from .quasistatic_copper_area import estimate_branch_capacitance


CONTRACT = "spike/pdn-shunt-capacitance/v1"


def _label(value: Any, name: str) -> str:
    if (not isinstance(value, str) or not value.strip() or len(value) > 80
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        raise ValueError(f"{name} must be an explicit nonempty string of at most 80 characters without controls")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} must be a finite SI number")
    result = float(value)
    if not np.isfinite(result):
        raise ValueError(f"{name} must be a finite SI number")
    return result


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def _snapshot(value: Any) -> Any:
    """Freeze JSON-shaped input with a bounded serialized size before admission."""
    chunks = []
    size = 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, separators=(",", ":"), allow_nan=False).iterencode(value):
            size += len(chunk.encode("utf-8"))
            if size > 8 * 1024 * 1024:
                raise ValueError("Capacitance input exceeds the 8 MiB JSON bound")
            chunks.append(chunk)
        return json.loads("".join(chunks))
    except (TypeError, RecursionError, OverflowError) as error:
        raise ValueError("Capacitance input must be bounded JSON data") from error


def _metadata(request: Mapping[str, Any]) -> dict:
    context = _label(request.get("context_digest"), "context_digest")
    if len(context) != 64 or any(c not in "0123456789abcdef" for c in context):
        raise ValueError("context_digest must be a lowercase SHA-256 digest")
    boundary = request.get("return_boundary")
    if (not isinstance(boundary, dict) or set(boundary) != {"mode", "node", "net"}
            or boundary.get("mode") != "explicit"):
        raise ValueError("An explicit return_boundary is required; no ground is inferred")
    _label(boundary.get("node"), "return_boundary.node")
    _label(boundary.get("net"), "return_boundary.net")
    provenance = request.get("provenance")
    if not isinstance(provenance, dict) or not provenance:
        raise ValueError("Nonempty source provenance is required")
    if set(provenance) == {"source"}:
        _label(provenance["source"], "provenance.source")
    elif set(provenance) == {"extractor", "geometry_digest", "extraction"}:
        if (provenance["extractor"] != "quasistatic_copper_area.estimate_branch_capacitance"
                or not isinstance(provenance["extraction"], dict)
                or provenance["extraction"].get("complete_source_coverage") is not True
                or provenance["extraction"].get("status") != "approximate"
                or request.get("model_status") != "approximate"
                or request.get("kind") != "supplied_lumped"):
            raise ValueError("Unknown or unqualified geometry extraction provenance")
        geometry_digest = provenance["geometry_digest"]
        if not isinstance(geometry_digest, str) or len(geometry_digest) != 64 or any(
                c not in "0123456789abcdef" for c in geometry_digest):
            raise ValueError("Geometry provenance requires a SHA-256 digest")
    else:
        raise ValueError("Unknown provenance shape: supply source or known geometry extraction evidence")
    status = request.get("model_status")
    if status not in {"supplied", "approximate", "experimental", "reference_validated"}:
        raise ValueError("Unsupported or failed capacitance model status")
    mesh = request.get("mesh", {"status": "not_applicable"})
    if not isinstance(mesh, dict) or mesh.get("status") not in {"accepted", "not_applicable"}:
        raise ValueError("Missing, defective or unaccepted mesh")
    allowed_mesh = {"status", "digest", "defects", "negative_energy"} if mesh["status"] == "accepted" else {"status"}
    if (set(mesh) - allowed_mesh or ("defects" in mesh and not isinstance(mesh["defects"], list))
            or ("negative_energy" in mesh and not isinstance(mesh["negative_energy"], bool))):
        raise ValueError("Unknown or mistyped mesh evidence field")
    if mesh.get("defects") or mesh.get("negative_energy"):
        raise ValueError("Mesh defects or negative energy forbid capacitance admission")
    if mesh.get("status") == "accepted":
        mesh_digest = mesh.get("digest")
        if not isinstance(mesh_digest, str) or len(mesh_digest) != 64 or any(
                c not in "0123456789abcdef" for c in mesh_digest):
            raise ValueError("Accepted mesh requires a SHA-256 digest")
    return {"context_digest": context, "return_boundary": deepcopy(boundary),
            "provenance": deepcopy(provenance), "model_status": status,
            "mesh": deepcopy(mesh), "model": _label(request.get("model"), "model")}


def normalize_shunt_capacitance(request: Mapping[str, Any], *, expected_context_digest: str | None = None) -> dict:
    """Admit supplied lumped edges or a reduced explicit-return Maxwell matrix.

    Required metadata: model, model_status, provenance, context_digest and
    return_boundary={mode:'explicit', node:..., net:...}. This validates supplied
    evidence consistency; it cannot authenticate external accuracy claims.
    Matrix inputs need nodes and matrix_f (max 128 conductors). Lumped inputs
    need elements with unique id, node_a, node_b and strictly positive SI F.
    Grounded matrices exclude the explicit return from nodes. Every conductor
    remains present; no floating conductor is silently grounded or eliminated.
    """
    if not isinstance(request, Mapping):
        raise ValueError("Capacitance request must be an object")
    common = {"kind", "model", "model_status", "provenance", "context_digest", "return_boundary"}
    fields = {"supplied_lumped": {"elements"}, "supplied_maxwell_matrix": {"nodes", "matrix_f"}}
    kind = request.get("kind")
    if not isinstance(kind, str) or kind not in fields:
        raise ValueError("Unknown capacitance source kind")
    required = common | fields[kind]
    if not required <= set(request) or set(request) - required - {"mesh"}:
        raise ValueError("Unknown or missing capacitance fields for source kind")
    request = _snapshot(dict(request))
    metadata = _metadata(request)
    if expected_context_digest is not None and metadata["context_digest"] != expected_context_digest:
        raise ValueError("Capacitance source context does not match the current analysis")
    ground = metadata["return_boundary"]["node"]
    kind = request.get("kind")
    elements = []
    if kind == "supplied_lumped":
        source = request.get("elements")
        if not isinstance(source, list) or not 1 <= len(source) <= 8192:
            raise ValueError("Supply 1..8192 capacitance elements")
        ids = set()
        for item in source:
            if not isinstance(item, dict) or set(item) != {"id", "node_a", "node_b", "capacitance_f"}:
                raise ValueError("Each capacitance element requires exactly id, node_a, node_b, capacitance_f")
            identity = _label(item.get("id"), "element.id")
            a, b = _label(item.get("node_a"), "node_a"), _label(item.get("node_b"), "node_b")
            value = _number(item.get("capacitance_f"), "capacitance_f")
            if identity in ids or a == b or value <= 0:
                raise ValueError("Duplicate ID, self-edge or nonpositive capacitance")
            ids.add(identity)
            elements.append({"id": identity, "node_a": a, "node_b": b, "capacitance_f": value})
    elif kind == "supplied_maxwell_matrix":
        nodes = request.get("nodes")
        if (not isinstance(nodes, list) or not 1 <= len(nodes) <= 128
                or any(not isinstance(v, str) or not v.strip() for v in nodes)
                or len(set(nodes)) != len(nodes) or ground in nodes):
            raise ValueError("Matrix needs 1..128 unique non-return conductor nodes")
        for label in nodes:
            _label(label, "nodes")
        raw = request.get("matrix_f")
        if not isinstance(raw, list) or len(raw) != len(nodes):
            raise ValueError("Matrix dimensions differ from conductor nodes")
        if any(not isinstance(row, list) or len(row) != len(nodes) for row in raw):
            raise ValueError("Matrix must be square")
        matrix = np.array([[_number(v, "matrix_f") for v in row] for row in raw])
        scale = float(np.max(np.abs(matrix)))
        if scale <= 0 or not np.allclose(matrix / scale, matrix.T / scale, rtol=0, atol=1e-12):
            raise ValueError("Maxwell matrix must be reciprocal and nonzero")
        # Symmetry tolerance only admits round-off; edge signs and row sums are
        # deliberately strict rather than hiding negative capacitance by clipping.
        matrix = .5 * matrix + .5 * matrix.T
        if np.min(np.linalg.eigvalsh(matrix / scale)) <= 1e-12:
            raise ValueError("Maxwell matrix lacks well-conditioned positive energy")
        for i, a in enumerate(nodes):
            shunt = float(np.sum(matrix[i]))
            if not np.isfinite(shunt) or shunt < 0:
                raise ValueError("Negative return capacitance: not a passive capacitor graph")
            if shunt > 0:
                elements.append({"id": f"ground-{i}", "node_a": a, "node_b": ground, "capacitance_f": shunt})
            for j in range(i):
                mutual = -float(matrix[i, j])
                if mutual < 0:
                    raise ValueError("Positive off-diagonal is not a passive Maxwell capacitor graph")
                if mutual > 0:
                    elements.append({"id": f"mutual-{j}-{i}", "node_a": nodes[j],
                                     "node_b": a, "capacitance_f": mutual})
    else:
        raise ValueError("Unknown capacitance source kind")
    # Every component must reach the explicitly prescribed return. In
    # particular a net named GND cannot substitute for the selected node.
    reached = {ground}
    pending = list(elements)
    while pending:
        remaining = []
        for edge in pending:
            if edge["node_a"] in reached or edge["node_b"] in reached:
                reached.update((edge["node_a"], edge["node_b"]))
            else:
                remaining.append(edge)
        if len(remaining) == len(pending):
            raise ValueError("Capacitance network contains an unreferenced floating component")
        pending = remaining
    result = {"contract": CONTRACT, "kind": kind, "elements": elements, **metadata,
              "validity": ["Admitted supplied/approximate circuit data, not arbitrary-PCB extraction qualification",
                           "Mutual conductor states retained; return potential explicitly prescribed"]}
    result["source_digest"] = _digest(request)
    return result


def pdn_capacitor_elements(request: Mapping[str, Any], *, expected_context_digest: str) -> list[dict]:
    """Normalize and adapt to pdn_network generic two-terminal capacitor stamps.

    Return the full normalization envelope alongside these elements in saved
    studies: the compact solver provenance points back to its source digest.
    Supplied Maxwell data is not mislabeled as geometry-extracted evidence.
    """
    _label(expected_context_digest, "expected_context_digest")
    result = normalize_shunt_capacitance(request, expected_context_digest=expected_context_digest)
    kind = ("extracted" if result["model_status"] != "supplied" and result["provenance"].get("extractor") ==
            "quasistatic_copper_area.estimate_branch_capacitance" else "supplied")
    return [{"id": edge["id"], "type": "capacitor", "positive": edge["node_a"],
             "negative": edge["node_b"], "capacitance_f": edge["capacitance_f"],
             "provenance": {"kind": kind, "source_id": result["source_digest"]}}
            for edge in result["elements"]]


def estimate_geometry_shunts(design: SpiDeR, spec: AnalysisSpec, branches: Sequence[Any],
                             node_by_net: Mapping[str, str], reference_node: str,
                             context_digest: str, mesh: dict) -> dict:
    """Reuse complete explicit-return unique-area geometry estimates.

    Caller explicitly shorts each selected net to its specified circuit node.
    This deliberately refuses lossy dielectric projection, vias, incomplete
    coverage and ambiguity. No new geometry or field solution is invented.
    """
    if (not isinstance(design, SpiDeR) or not isinstance(spec, AnalysisSpec)
            or not isinstance(mesh, dict) or not isinstance(node_by_net, Mapping)
            or any(not isinstance(branch, MeshBranch) for branch in branches)):
        raise ValueError("Geometry adapter requires typed design, spec, branches and explicit maps")
    design, spec, branches, mesh, node_by_net = deepcopy((design, spec, list(branches), mesh, dict(node_by_net)))
    _snapshot({"design": asdict(design), "spec": asdict(spec), "branches": [asdict(branch) for branch in branches],
               "mesh": mesh, "node_by_net": node_by_net})
    for net in node_by_net:
        _label(net, "node_by_net key")
    reference_node = _label(reference_node, "reference_node")
    return_net = spec.return_path.get("net")
    if spec.return_path.get("mode") != "explicit" or not return_net:
        raise ValueError("Geometry estimate requires an explicit physical return net")
    if mesh.get("status") != "accepted" or not mesh.get("digest"):
        raise ValueError("Geometry estimate requires accepted digest-bound mesh evidence")
    if mesh.get("digest") != _digest([asdict(branch) for branch in branches]):
        raise ValueError("Mesh digest does not match the supplied branches")
    if not node_by_net or return_net in node_by_net:
        raise ValueError("Select signal nets explicitly, excluding return")
    nodes = [_label(value, "node_by_net") for value in node_by_net.values()]
    if len(set(nodes)) != len(nodes) or reference_node in nodes:
        raise ValueError("Signal nets require distinct non-return circuit nodes")
    selected_nets = set(node_by_net) | {return_net}
    if any(str(via.get("net_name") or via.get("net") or "") in selected_nets for via in design.vias):
        raise ValueError("Via capacitance is unsupported by the planar geometry surrogate")
    for collection in (design.tracks, design.pads, design.zones):
        ids = [item.get("id") for item in collection
               if str(item.get("net_name") or item.get("net") or "") in selected_nets]
        if any(not isinstance(identity, str) or not identity for identity in ids) or len(set(ids)) != len(ids):
            raise ValueError("Geometry requires unique explicit source object IDs")
    selected = [branch for branch in branches if branch.net in node_by_net]
    if set(node_by_net) != {branch.net for branch in selected}:
        raise ValueError("Every selected net requires represented copper branches")
    values, losses, info = estimate_branch_capacitance(design, spec, selected)
    if info.get("status") != "approximate" or info.get("complete_source_coverage") is not True:
        raise ValueError("Incomplete or ambiguous copper/reference geometry cannot supply PDN capacitance")
    if np.any(losses != 0):
        raise ValueError("Lossy geometry requires a frequency-dependent dielectric model")
    elements = []
    for net, node in node_by_net.items():
        value = sum(float(values[i]) for i, branch in enumerate(selected) if branch.net == net)
        elements.append({"id": f"geometry-{net}", "node_a": node,
                         "node_b": reference_node, "capacitance_f": value})
    request = {"kind": "supplied_lumped", "elements": elements,
               "model": info["model"], "model_status": "approximate", "mesh": mesh,
               "context_digest": context_digest,
               "return_boundary": {"mode": "explicit", "net": return_net, "node": reference_node},
               "provenance": {"extractor": "quasistatic_copper_area.estimate_branch_capacitance",
                              "geometry_digest": _digest(asdict(design)), "extraction": info}}
    result = normalize_shunt_capacitance(request)
    result["validity"].extend(info["validity"])
    result["validity"].append("Each selected net is explicitly collapsed to one equipotential node")
    return result
