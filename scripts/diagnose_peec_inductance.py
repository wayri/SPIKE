# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Reproduce native PEEC energy defects without returning an AC solution."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from python.spike_core.contracts import AnalysisSpec
from python.spike_core.hybrid_mesh import build_hybrid_mesh, TOPOLOGY_ONLY_BRANCH_KINDS
from python.spike_core.peec_plugin import _make_native_solver, native
from python.spike_core.peec_network import dense
from python.spike_core.service import _design_from_kicad


def diagnose(board: Path, net: str, size: float) -> dict:
    if native is None:
        raise RuntimeError("Native PEEC extension is required.")
    design = _design_from_kicad(str(board))
    # Bound meshing to retained real geometry, preserving the imported stackup.
    for field in ("tracks", "vias", "pads", "zones"):
        setattr(design, field, [item for item in getattr(design, field)
                               if str(item.get("net_name", item.get("net", ""))) == net])
    spec = AnalysisSpec(**{"mode": "ac", "net_names": [net],
        "mesh": {"target_size_mm": size, "zone_cell_mm": size,
                 "max_conductors": 500, "max_zone_cells": 250}})
    mesh = build_hybrid_mesh(design, spec)
    if mesh.truncated:
        raise ValueError("Diagnostic mesh resource limit reached; no partial matrix accepted.")
    branches = [b for b in mesh.branches if b.kind not in TOPOLOGY_ONLY_BRANCH_KINDS]
    if not branches:
        raise ValueError("No physical branches for selected net.")
    physical = dataclasses.replace(mesh, branches=branches)
    solver, _ = _make_native_solver(physical, 4.2, spec)
    matrix = dense(solver.compute_partial_inductance())
    eigen = np.linalg.eigvalsh(matrix)
    diagonal = np.diag(matrix)
    denom = np.sqrt(np.maximum(diagonal[:, None]*diagonal[None, :], 0))
    ratio = np.divide(np.abs(matrix), denom, out=np.full_like(matrix, np.inf), where=denom > 0)
    np.fill_diagonal(ratio, 0)
    i, j = np.unravel_index(np.argmax(ratio), ratio.shape)
    barrel = [k for k, branch in enumerate(branches) if branch.kind in {"via", "pad_barrel"}]
    via_eigen = np.linalg.eigvalsh(matrix[np.ix_(barrel, barrel)]) if barrel else np.array([])
    return {"contract": "spike/peec-energy-diagnostic/v1", "production_qualified": False,
        "board_sha256": hashlib.sha256(board.read_bytes()).hexdigest(), "net": net,
        "native_sha256": hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        "mesh_size_mm": size, "physical_branch_count": len(branches),
        "minimum_eigenvalue_h": float(eigen[0]),
        "negative_eigenvalues_h": eigen[eigen < 0].tolist(),
        "barrel_eigenvalues_h": via_eigen.tolist(),
        "worst_pair_indices": [int(i), int(j)], "worst_coupling_ratio": float(ratio[i, j]),
        "branches": [dataclasses.asdict(branch) for branch in branches],
        "inductance_h": matrix.tolist(),
        "limits": ["Imported board-derived diagnostic; no reviewed operating terminals.",
                   "Eigenvalues diagnose magnetic energy only, not board impedance accuracy."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, required=True)
    parser.add_argument("--net", required=True)
    parser.add_argument("--size-mm", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not np.isfinite(args.size_mm) or args.size_mm <= 0:
        parser.error("size-mm must be positive and finite")
    report = diagnose(args.board, args.net, args.size_mm)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("physical_branch_count", "minimum_eigenvalue_h", "worst_coupling_ratio")}))
