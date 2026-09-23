"""Count-based 30-Marble resource probe; NOT a mesh, renderer or solver benchmark."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.spike_core.assembly_resources import GIB, estimate_assembly_resources


def main():
    # Counts from pinned Marble v1.4.4 inspection, not reconstructed geometry.
    design = {"design_id": "marble-count-proxy",
              "layers": [{"name": f"L{i}.Cu", "layer_type": "copper"} for i in range(30)]}
    for key, count in {"tracks": 37380, "vias": 3664, "pads": 5272,
                       "zones": 124, "components": 997, "nets": 1374}.items():
        design[key] = [{} for _ in range(count)]
    rows = []
    for count in (1, 10, 20, 30):
        assembly = {"assembly_id": "scale-probe", "name": "Count proxy", "boards": [
            {"id": f"board-{i}", "design_id": "marble-count-proxy"} for i in range(count)]}
        for workload in ("visualization", "pi_dc", "pi_ac", "thermal", "full_wave"):
            started = perf_counter()
            result = estimate_assembly_resources(assembly, {"marble-count-proxy": design},
                workload=workload, memory_limit_gb=32, physical_memory_bytes=64 * GIB)
            rows.append({"boards": count, "workload": workload,
                         "estimated_gib": round(result["estimated_workspace_gb"], 3),
                         "admitted": result["can_admit"],
                         "seconds": round(perf_counter() - started, 6),
                         "issues": [item["code"] for item in result["issues"]]})
    print(json.dumps({"kind": "count_proxy_resource_estimate", "geometry_loaded": False,
                      "solver_executed": False, "configured_gib": 32,
                      "assumed_machine_gib": 64, "results": rows}, indent=2))


if __name__ == "__main__":
    main()
