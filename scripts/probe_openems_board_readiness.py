# SPDX-License-Identifier: Apache-2.0
"""Record bounded openEMS admission evidence for an existing KiCad board.

This does not create ports, infer materials, or run a field solve.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from extensions.openems_suite.engine import _validate_openems_case
from python.spike_core.cli import load_design
from python.spike_core.contracts import AnalysisSpec, DesignIR


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("--net", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mesh-mm", type=float, default=1.0)
    args = parser.parse_args()
    board = args.board.resolve(strict=True)
    started = time.perf_counter()
    design = DesignIR(**load_design(board))
    imported_s = time.perf_counter() - started
    spec = AnalysisSpec(mode="si", solver_id="external.openems", net_names=[args.net],
                        frequency_start_hz=1e8, frequency_stop_hz=1e9,
                        frequency_points=11)
    validation = _validate_openems_case(design, spec, {"mesh_resolution_mm": args.mesh_mm})
    blocker_codes = Counter(issue["code"] for issue in validation["run_blockers"])
    report = {
        "contract": "spike/openems-board-readiness-probe/v1",
        "board": str(board),
        "board_sha256": hashlib.sha256(board.read_bytes()).hexdigest(),
        "net": args.net,
        "frequency_hz": [1e8, 1e9],
        "mesh_resolution_mm": args.mesh_mm,
        "import_seconds": imported_s,
        "preflight_seconds": time.perf_counter() - started - imported_s,
        "design_counts": {key: len(getattr(design, key)) for key in
                          ("layers", "stackup", "nets", "tracks", "zones", "vias", "pads")},
        "runtime": {key: validation["engine"].get(key) for key in
                    ("state", "version", "adapter_version", "model_status")},
        "can_prepare": validation["can_prepare"],
        "can_run": validation["can_run"],
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "run_blocker_count": len(validation["run_blockers"]),
        "run_blocker_codes": dict(blocker_codes),
        "run_blocker_examples": validation["run_blockers"][:8],
        "resources": validation["resources"],
        "field_solve_executed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("board", "net", "can_prepare", "can_run", "errors",
                       "run_blocker_count", "run_blocker_codes", "resources")},
                     indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
