# SPDX-License-Identifier: Apache-2.0
"""Bounded external mesh admission, separate from analysis result admission."""
from __future__ import annotations

import copy
import json
import math
import re


MESH_CONTRACTS = {"spike/gmsh-mesh/v1", "spike/emerge-mesh/v1", "spike/openems-grid/v1"}


def admit_extension_mesh(raw: object, binding: dict, *, extension_id: str) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("contract"), str) or raw["contract"] not in MESH_CONTRACTS:
        raise ValueError("Unsupported extension mesh contract.")
    if raw["contract"] == "spike/gmsh-mesh/v1":
        from .gmsh_extension_mesh import admit_gmsh_mesh
        return admit_gmsh_mesh(raw, binding, extension_id=extension_id)
    if raw.get("status") != "completed" or raw.get("solved") is not False or raw.get("units") != "mm":
        raise ValueError("External mesh must be completed, unsolved and in millimetres.")
    if not isinstance(raw.get("model_status"), str) or raw["model_status"] not in {"unvalidated", "experimental"}:
        raise ValueError("Mesh admission cannot grant physics validation.")
    if raw.get("coordinate_frame") != "design_top_copper":
        raise ValueError("External mesh requires the design top-copper coordinate frame.")
    provenance = raw.get("provenance", {})
    if not isinstance(provenance, dict) or provenance.get("design_id") != binding["design_id"] or provenance.get("design_digest_sha256") != binding["digest_sha256"]:
        raise ValueError("Extension mesh does not match the current design binding.")
    for key in ("case_sha256", "generated_script_sha256"):
        if not re.fullmatch(r"[a-f0-9]{64}", str(provenance.get(key, ""))):
            raise ValueError(f"Mesh provenance requires {key}.")
    if len(json.dumps(raw, allow_nan=False).encode()) > 32 * 1024 * 1024:
        raise ValueError("External mesh exceeds the 32 MiB admission limit.")
    finite = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    if raw["contract"] == "spike/emerge-mesh/v1":
        nodes, tets, triangles = raw.get("nodes_mm"), raw.get("tetrahedra"), raw.get("triangles")
        if not isinstance(nodes, list) or not 4 <= len(nodes) <= 100000 or any(not isinstance(n, list) or len(n) != 3 or not all(finite(v) for v in n) for n in nodes):
            raise ValueError("Mesh nodes require bounded finite XYZ coordinates.")
        for values, count, cap in ((tets, 4, 200000), (triangles, 3, 200000)):
            if not isinstance(values, list) or len(values) > cap or any(not isinstance(cell, list) or len(cell) != count or any(type(i) is not int or not 0 <= i < len(nodes) for i in cell) or len(set(cell)) != count for cell in values):
                raise ValueError("Mesh connectivity is malformed or exceeds bounds.")
        if not tets:
            raise ValueError("Tetrahedral mesh contains no volume cells.")
        # Scale-independent degeneracy check, not a quality/convergence claim.
        import numpy as np
        coords = np.asarray(nodes, dtype=float)[np.asarray(tets, dtype=int)]
        with np.errstate(over="ignore", invalid="ignore"):
            edges = coords[:, 1:] - coords[:, :1]
        scales = np.max(np.abs(edges), axis=(1, 2))
        if not np.all(np.isfinite(edges)) or not np.all(np.isfinite(scales)) or np.any(scales == 0):
            raise ValueError("Degenerate or nonfinite tetrahedron scale.")
        relative = edges / scales[:, None, None]
        determinants = np.linalg.det(relative)
        if not np.all(np.isfinite(determinants)) or np.any(np.abs(determinants) < 1e-14):
            raise ValueError("Degenerate tetrahedron.")
    else:
        grid = raw.get("lines_mm")
        if not isinstance(grid, dict) or set(grid) != {"x", "y", "z"}:
            raise ValueError("FDTD grid requires XYZ grid lines.")
        for axis in grid.values():
            if not isinstance(axis, list) or not 2 <= len(axis) <= 100000 or not all(finite(v) for v in axis) or any(b <= a for a, b in zip(axis, axis[1:])):
                raise ValueError("FDTD grid lines must be finite and strictly increasing.")
    result = copy.deepcopy(raw)
    result["provenance"]["extension_id"] = extension_id
    result["admission"] = {"contract": "spike/extension-mesh-admission/v1", "design_bound": True,
        "complete_connectivity": True, "physics_validated": False,
        "cross_engine_reuse": False}
    return result
