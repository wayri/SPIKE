# SPDX-License-Identifier: Apache-2.0
"""Reproduce the original supplied-RLGC spatial voltage example; no EM solve."""
import json
from hashlib import sha256
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from python.spike_core.service_si_spatial import run_si_spatial_pair
from python.spike_core.spider_v2 import SpiDeRV2


def build():
    directory = Path(__file__).resolve().parent
    design = {"contract": "spike/design-ir/v2", "design_id": "original-si-spatial-pair", "name": "Supplied RLGC crosstalk pair",
        "source": {"source_format": "spike-original-fixture", "source_digest": sha256(b"SPIKE original spatial-pair fixture v1: 80mm, 1mm spacing, 0.2mm strokes").hexdigest()},
        "layers": [{"id": "top", "name": "F.Cu", "layer_type": "copper", "z_mm": 0., "thickness_mm": .035}],
        "nets": [{"id": "aggressor-net", "name": "AGGRESSOR"}, {"id": "victim-net", "name": "VICTIM"}],
        "tracks": [{"id": "aggressor-stroke", "net_id": "aggressor-net", "layer_id": "top", "start_mm": [0., 0.], "end_mm": [80., 0.], "width_mm": .2},
                   {"id": "victim-stroke", "net_id": "victim-net", "layer_id": "top", "start_mm": [0., 1.], "end_mm": [80., 1.], "width_mm": .2}]}
    design = SpiDeRV2.from_dict(design).to_dict()
    pair = json.loads((ROOT / "examples/rlgc_coupled_pair/symmetric-pair.request.json").read_text())
    pair["conductor_ids"] = ["aggressor-net", "victim-net"]
    pair["probes"] = [{"id": f"sample-{i}", "fractional_position": i / 31} for i in range(32)]
    for excitation in pair["excitations"]:
        excitation["incident_waves"] = [{"real": 1., "imag": 0.}, {"real": 0., "imag": 0.}, {"real": 0., "imag": 0.}, {"real": 0., "imag": 0.}]
    request = {"design": design, "occurrence_id": "active-board", "aggressor_net_id": "aggressor-net",
               "victim_net_id": "victim-net", "request_id": "original-spatial-pair-1", "pair_request": pair,
               "aggressor_segment_id": "aggressor-stroke", "victim_segment_id": "victim-stroke"}
    result = run_si_spatial_pair(request)
    normalized = {"contract": "spike/design-snapshot/v1", "canonical_design": design,
                  "design": SpiDeRV2.from_dict(design).to_v1().to_dict()}
    for name, value in (("board.spike-design.json", normalized), ("solver.json", {key: request[key] for key in ("pair_request", "aggressor_segment_id", "victim_segment_id")}), ("design.json", design), ("setup.json", request), ("samples.json", result["data"]), ("evidence.json", result)):
        (directory / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


if __name__ == "__main__": build()
