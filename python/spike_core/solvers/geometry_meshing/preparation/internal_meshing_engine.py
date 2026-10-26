# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Versioned, bounded application boundary for SPIKE-owned tetra meshing."""
from __future__ import annotations

import hashlib
import json

from .tetra_mesh_refinement import TetraRefinementError, _require

CONTROL_LIMIT_BYTES = 8 * 1024 * 1024
REQUEST_CONTRACT = "spike/internal-mesh-request/v1"
RESULT_CONTRACT = "spike/internal-mesh-result/v1"


def _canonical(value):
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise TetraRefinementError("Mesh controls must be finite JSON data.") from exc
    _require(len(encoded) <= CONTROL_LIMIT_BYTES, "Mesh control size exceeds 8 MiB.")
    return encoded


def internal_mesh_capabilities():
    """Describe executable scopes without promoting solver qualification."""
    return {
        "contract": "spike/internal-mesh-capability/v1",
        "engine": "spike-internal-tetra-v1", "status": "experimental",
        "request_contract": REQUEST_CONTRACT, "result_contract": RESULT_CONTRACT,
        "operations": ["generate", "adapt", "optimize"],
        "generation_domain": "convex_point_cloud",
        "adaptation": ["indicator_bulk_marking", "edge_length", "manual_edges"],
        "preserved": ["material_ids", "source_ownership", "boundary_labels"],
        "limits": {"control_bytes": CONTROL_LIMIT_BYTES, "cells": 5000,
                   "vertices": 10000, "generation_points": 128,
                   "manual_edges": 256, "scalar_fields": 32},
        "unsupported": ["nonconvex_CAD_generation", "constrained_surface_recovery",
                        "coarsening", "moving_CAD", "curved_high_order_cells",
                        "boundary_layers", "distributed_meshing"],
        "external_mesher_required": False, "production_qualified": False,
    }


def run_internal_meshing(request):
    """Execute one atomic candidate pass; inputs remain immutable.

    The caller must solve again and supply updated indicators between passes.
    Meshing evidence establishes geometry properties, not physics convergence.
    No executable paths, scripts, native snippets, or filesystem paths accepted.
    """
    encoded = _canonical(request)
    _require(isinstance(request, dict) and
             set(request) == {"contract", "operation", "parameters"},
             "Unexpected internal mesh request fields.")
    _require(request["contract"] == REQUEST_CONTRACT, "Unsupported internal mesh contract.")
    operation, params = request["operation"], request["parameters"]
    _require(isinstance(operation, str) and operation in ("generate", "adapt", "optimize"),
             "Unsupported internal mesh operation.")
    _require(isinstance(params, dict), "Mesh parameters must be an object.")
    for key, lower, upper in (("max_cells", 1, 5000), ("max_vertices", 4, 10000),
                               ("iterations", 1, 10)):
        if key in params:
            _require(type(params[key]) is int and lower <= params[key] <= upper,
                     "Invalid internal mesh resource or iteration budget.")
    if operation == "generate":
        from .internal_tetra_generation import generate_tetra_mesh
        allowed = {"points", "units", "material_id", "source_object_id", "boundary_label",
                   "max_cells", "optimize", "iterations", "protected_vertices"}
        _require("points" in params and set(params) <= allowed, "Unexpected generation fields.")
        optimize = params.get("optimize", True)
        _require(type(optimize) is bool, "Optimization control must be boolean.")
        generation_params = {key: value for key, value in params.items()
                             if key not in {"optimize", "iterations", "protected_vertices"}}
        points = generation_params.pop("points")
        candidate = generate_tetra_mesh(points, **generation_params)
        if optimize:
            from .tetra_mesh_optimization import optimize_tetra_mesh
            optimized = optimize_tetra_mesh(candidate["mesh"], candidate["boundary_triangles"],
                                            iterations=params.get("iterations", 3),
                                            protected_vertices=params.get("protected_vertices"))
            candidate["generation_quality"] = candidate["quality"]
            candidate["evidence"]["scope"] = "before_quality_optimization"
            candidate["evidence"]["final_weak_delaunay_asserted"] = False
            candidate.update(optimized)
        else:
            _require("protected_vertices" not in params and "iterations" not in params,
                     "Inactive optimization controls are not accepted.")
    elif operation == "adapt":
        from .dynamic_tetra_adaptation import adapt_tetra_mesh
        allowed = {"mesh", "boundary_triangles", "cell_indicators", "marking_fraction",
                   "target_edge_length", "manual_edges", "protected_vertices", "optimize",
                   "iterations", "max_cells", "max_vertices", "nodal_fields", "cell_fields"}
        _require({"mesh", "boundary_triangles"} <= set(params) and set(params) <= allowed,
                 "Unexpected adaptation fields.")
        candidate = adapt_tetra_mesh(**params)
    else:
        from .tetra_mesh_optimization import optimize_tetra_mesh
        allowed = {"mesh", "boundary_triangles", "protected_vertices", "iterations"}
        _require({"mesh", "boundary_triangles"} <= set(params) and set(params) <= allowed,
                 "Unexpected optimization fields.")
        candidate = optimize_tetra_mesh(**params)
    mesh_digest = hashlib.sha256(_canonical(candidate["mesh"])).hexdigest()
    result = {"contract": RESULT_CONTRACT, "engine": "spike-internal-tetra-v1",
              "operation": operation, "status": "completed", "candidate": candidate,
              "request_sha256": hashlib.sha256(encoded).hexdigest(),
              "mesh_sha256": mesh_digest,
              "candidate_sha256": hashlib.sha256(_canonical(candidate)).hexdigest(),
              "production_qualified": False}
    _canonical(result)
    return result
