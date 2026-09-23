# SPDX-License-Identifier: MIT
# Copyright (c) 2026 SigHarmonic
"""Run a reproducible geometry-to-service crosstalk example, not measured data."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.design_ir_v2 import DesignIRV2, Layer, Material, Net, SourceIdentity, Track, Zone
from python.spike_core.service import handle


def example():
    copper = Material(id="cu", name="Copper", material_class="conductor", conductivity_s_per_m=5.8e7)
    dielectric = Material(id="core", name="Homogeneous example dielectric", material_class="dielectric", relative_permittivity=4., loss_tangent=.015)
    design = DesignIRV2(design_id="si-two-line-example", name="50 mm parallel traces",
        source=SourceIdentity(source_format="fixture", source_digest=hashlib.sha256(b"SPIKE SI two-line example v1").hexdigest()),
        materials=[copper, dielectric],
        layers=[Layer(id="signal", name="F.Cu", layer_type="copper", order=0, z_mm=0., thickness_mm=.035, material_id="cu"),
                Layer(id="dielectric", name="Core", layer_type="dielectric", order=1, z_mm=.035, thickness_mm=.2, material_id="core"),
                Layer(id="reference", name="In1.Cu", layer_type="copper", order=2, z_mm=.235, thickness_mm=.035, material_id="cu")],
        nets=[Net(id="a", name="AGGRESSOR"), Net(id="v", name="VICTIM"), Net(id="g", name="GND")],
        tracks=[Track(id="a1", net_id="a", layer_id="signal", start_mm=(0.,0.), end_mm=(50.,0.), width_mm=.35),
                Track(id="v1", net_id="v", layer_id="signal", start_mm=(0.,.8), end_mm=(50.,.8), width_mm=.35)],
        zones=[Zone(id="ground", net_id="g", layer_ids=["reference"], outlines_mm=[[(-5.,-5.),(55.,-5.),(55.,5.),(-5.,5.)]])])
    waveform = np.zeros(512)
    waveform[16:24] = np.linspace(0, 1, 8)
    waveform[24:80] = 1
    waveform[80:88] = np.linspace(1, 0, 8)
    request = {"contract": "spike/si-uniform-channel-request/v1", "signal_net": "AGGRESSOR",
        "victim_net": "VICTIM", "reference_net": "GND", "reference_layer": "In1.Cu",
        "reference_impedance_ohm": 50., "frequencies_hz": np.linspace(0, 8e9, 513).tolist(),
        "cross_section_vertical_cells": 24, "trace_limit": 513,
        "crosstalk_model": {"port_map": {"aggressor_near": 0, "victim_near": 1, "aggressor_far": 2, "victim_far": 3},
            "termination_ohm": [35.,75.,50.,100.], "waveform_v": waveform.tolist(), "trace_limit": 513}}
    response = handle({"id": "si-crosstalk-example", "method": "run_si_uniform_channel",
                       "params": {"design": design.to_dict(), "request": request}})
    if not response.get("ok"):
        raise RuntimeError(response)
    return design.to_dict(), request, response["result"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, payload in zip(("design.json", "request.json", "result.json"), example()):
        encoded = (json.dumps(payload, indent=2, allow_nan=False)+"\n").encode()
        (args.output/name).write_bytes(encoded)
        manifest[name] = hashlib.sha256(encoded).hexdigest()
    (args.output/"hashes.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"status": "completed", "output": str(args.output), "hashes": manifest}))
