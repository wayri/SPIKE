# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Bounded matrix-only Marble refinement probe; not an AC accuracy result."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
from python.spike_core.contracts import AnalysisSpec  # noqa: E402
from python.spike_core.hybrid_mesh import (  # noqa: E402
    TOPOLOGY_ONLY_BRANCH_KINDS,
    build_hybrid_mesh,
)
from python.spike_core.peec_plugin import native  # noqa: E402
from python.spike_core.peec_volume_adapter import extract_volume_matrices  # noqa: E402
from python.spike_core.service import _design_from_kicad  # noqa: E402


def probe(board: Path, mesh_size_mm: float, max_pairs: int, max_evaluations: int,
          max_pair_evaluations: int = 2_000_000) -> dict:
    if native is None:
        raise RuntimeError("Native PEEC extension is required.")
    design = _design_from_kicad(str(board))
    net = "Net-(C383-Pad1)"
    for field in ("tracks", "vias", "pads", "zones"):
        setattr(design, field, [item for item in getattr(design, field)
                               if str(item.get("net_name", item.get("net", ""))) == net])
    spec = AnalysisSpec(mode="ac", net_names=[net], mesh={
        "target_size_mm": mesh_size_mm, "zone_cell_mm": mesh_size_mm,
        "max_zone_cells": 1000, "max_conductors": 2000, "memory_budget_mb": 512,
    })
    mesh = build_hybrid_mesh(design, spec)
    if mesh.truncated:
        raise ValueError("Mesh resource limit reached; partial mesh rejected.")
    branches = [branch for branch in mesh.branches
                if branch.kind not in TOPOLOGY_ONLY_BRANCH_KINDS]
    options = native.VolumeMatrixIntegrationOptions()
    defaults = {
        "maximum_matrix_pairs": options.maximum_matrix_pairs,
        "maximum_total_potential_evaluations": options.maximum_total_potential_evaluations,
        "absolute_tolerance_h": options.pair.absolute_tolerance_h,
        "relative_tolerance": options.pair.relative_tolerance,
        "max_pair_potential_evaluations": options.pair.max_potential_evaluations,
    }
    options.maximum_matrix_pairs = max_pairs
    options.maximum_total_potential_evaluations = max_evaluations
    options.pair.max_potential_evaluations = max_pair_evaluations
    report = {
        "contract": "spike/marble-refinement-matrix-probe/v1",
        "production_qualified": False,
        "scope": "matrix-only diagnostic; no AC terminals or path QoI",
        "board_sha256": hashlib.sha256(board.read_bytes()).hexdigest(),
        "native_sha256": hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        "mesh_size_mm": mesh_size_mm,
        "physical_branch_count": len(branches),
        "matrix_pair_count": matrix_pair_count(len(branches)),
        "default_limits": defaults,
        "probe_limits": {"maximum_matrix_pairs": max_pairs,
                         "maximum_total_potential_evaluations": max_evaluations,
                         "max_pair_potential_evaluations": max_pair_evaluations},
        "per_pair_tolerances_changed": False,
        "limits": [
            "Isolated imported C383 rail; inferred operating terminals are not exercised.",
            "Mesh refinement and matrix passivity do not establish board impedance accuracy.",
        ],
    }
    started = time.perf_counter()
    try:
        extracted = extract_volume_matrices(native, design, branches, options)
    except ValueError as exc:
        report.update(status="failed", wall_time_seconds=time.perf_counter() - started,
                      error=str(exc))
        return report
    elapsed = time.perf_counter() - started
    inductance_eigenvalues = np.linalg.eigvalsh(extracted.inductance_h)
    resistance_eigenvalues = np.linalg.eigvalsh(extracted.dc_resistance_ohm)
    report.update({
        "status": "completed",
        "wall_time_seconds": elapsed,
        "minimum_inductance_eigenvalue_h": float(inductance_eigenvalues[0]),
        "negative_inductance_eigenvalue_count": int(np.count_nonzero(inductance_eigenvalues < -1e-18)),
        "minimum_resistance_eigenvalue_ohm": float(resistance_eigenvalues[0]),
        "quality": extracted.quality,
    })
    return report


def matrix_pair_count(physical_branch_count: int) -> int:
    """Return the symmetric matrix's stored upper-triangle pair count."""
    if physical_branch_count < 0:
        raise ValueError("physical branch count must be non-negative")
    return physical_branch_count * (physical_branch_count + 1) // 2


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", required=True, type=Path)
    parser.add_argument("--mesh-size-mm", required=True, type=float)
    parser.add_argument("--max-pairs", type=int, default=8000)
    parser.add_argument("--max-evaluations", type=int, default=300_000_000)
    parser.add_argument("--max-pair-evaluations", type=int, default=2_000_000)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if (args.mesh_size_mm <= 0 or args.max_pairs <= 0 or args.max_evaluations <= 0
            or args.max_pair_evaluations <= 0):
        parser.error("mesh size and limits must be positive")
    result = probe(args.board, args.mesh_size_mm, args.max_pairs, args.max_evaluations,
                   args.max_pair_evaluations)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, allow_nan=False))
