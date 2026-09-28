# SPDX-License-Identifier: Apache-2.0
"""Bounded, design-bound geometry and mesh input for process extensions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from .contracts import AnalysisSpec, DesignIR
from .hybrid_mesh import build_hybrid_mesh
from .meshing import MeshingEngine, MeshingOptions
from .solver_geometry import build_solver_geometry


MAX_EXCHANGE_BRANCHES = 8192
MAX_EXCHANGE_BYTES = 32 * 1024 * 1024


def build_extension_mesh_exchange(
    design_data: dict[str, Any], spec_data: Any, design_binding: dict[str, str],
) -> dict[str, Any]:
    """Export full admitted topology, a display preview, and solver inputs.

    Preview cells may be sampled. Only ``mesh`` contains the complete admitted
    topology, and a truncated or erroneous topology is never sent as a solve mesh.
    """
    if spec_data is None:
        spec_data = {}
    if not isinstance(spec_data, dict):
        raise ValueError("Extension mesh_spec must be an AnalysisSpec object.")
    design = DesignIR(**design_data)
    spec = AnalysisSpec(**spec_data)
    if not isinstance(spec.mesh, dict):
        raise ValueError("Extension mesh_spec.mesh must be an object.")
    mesh_options = dict(spec.mesh)
    requested = mesh_options.get("max_conductors", MAX_EXCHANGE_BRANCHES)
    if isinstance(requested, bool) or not isinstance(requested, int) or not 16 <= requested <= MAX_EXCHANGE_BRANCHES:
        raise ValueError(f"Extension mesh max_conductors must be 16–{MAX_EXCHANGE_BRANCHES}.")
    mesh_options["max_conductors"] = requested
    preview_cells = mesh_options.get("max_preview_cells", 5000)
    if isinstance(preview_cells, bool) or not isinstance(preview_cells, int) or not 100 <= preview_cells <= 25000:
        raise ValueError("Extension mesh max_preview_cells must be 100–25000.")
    mesh_options["max_preview_cells"] = preview_cells
    spec.mesh = mesh_options

    hybrid = build_hybrid_mesh(design, spec)
    if hybrid.truncated:
        raise ValueError("Extension mesh exceeded its admitted branch capacity; select fewer nets or a coarser mesh.")
    errors = [issue for issue in hybrid.issues if issue.severity == "error"]
    if errors:
        raise ValueError(f"Extension mesh has unsupported geometry: {errors[0].code}: {errors[0].message}")
    topology = {
        "contract": "spike/hybrid-mesh-exchange/v1",
        "units": "mm",
        "target_size_mm": hybrid.target_size_mm,
        "nodes": [asdict(node) for node in hybrid.nodes],
        "branches": [asdict(branch) for branch in hybrid.branches],
        "cells": hybrid.cells,
        "node_count": len(hybrid.nodes),
        "branch_count": len(hybrid.branches),
        "cell_count": len(hybrid.cells),
        "truncated": False,
        "issues": [asdict(issue) for issue in hybrid.issues],
        "branch_admission": hybrid.branch_admission,
    }
    encoded = json.dumps(topology, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_EXCHANGE_BYTES:
        raise ValueError("Extension mesh exceeds the 32 MB exchange limit; select fewer nets or a coarser mesh.")
    digest = hashlib.sha256(encoded).hexdigest()
    normalized_spec = spec.to_dict()
    spec_digest = hashlib.sha256(json.dumps(normalized_spec, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    preview = MeshingEngine().preview(design, spec, hybrid, MeshingOptions.from_spec(spec))
    return {
        "analysis_spec": normalized_spec,
        "solver_geometry": build_solver_geometry(design, spec),
        "mesh": topology,
        "mesh_preview": preview,
        "mesh_binding": {
            "contract": "spike/mesh-binding/v1",
            "design_id": design_binding["design_id"],
            "design_digest_sha256": design_binding["digest_sha256"],
            "mesh_digest_sha256": digest,
            "analysis_spec_digest_sha256": spec_digest,
        },
    }


__all__ = ["build_extension_mesh_exchange"]
