# SPDX-License-Identifier: Apache-2.0
"""Extract real ESP32 overlap parasitics and connect two occurrence SI models.

Board source geometry is pinned and explicitly clipped by the existing recipe.
Connector is an authored synthetic two-line RLGC model. This executes network
coupling and loaded crosstalk, without claiming spatial inter-board fields.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_esp32_si_crosstalk_example import build_slice, request
from python.spike_core.spider_v2 import SpiDeRV2
from python.spike_core.solvers.signal_integrity.channels.si_coupled_channel import extract_coupled_path_rlgc, multiconductor_rlgc_network
from python.spike_core.solvers.signal_integrity.networks.si_network_graph import build_network_graph
from python.spike_core.solvers.signal_integrity.networks.si_multiboard import model_digest
from python.spike_core.solvers.signal_integrity.receivers.si_crosstalk import analyze_crosstalk
from python.spike_core.solvers.signal_integrity.networks.sparameters import touchstone_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    output = parser.parse_args().output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    begin = time.perf_counter()
    design, model = build_slice(), request()
    extraction = extract_coupled_path_rlgc(SpiDeRV2.from_dict(design), model)
    network = multiconductor_rlgc_network(extraction, model["frequencies_hz"], 50.)
    leaf = {"kind": "touchstone", "name": "esp32-clipped-overlap.s4p",
            "text": touchstone_text(network.frequencies_hz, network.parameters, 50.)}
    connector = {"kind": "rlgc", "coupled": True, "length_m": .01,
                 "resistance_ohm_per_m": 10., "inductance_h_per_m": 250e-9,
                 "capacitance_f_per_m": 100e-12, "loss_tangent": .002,
                 "inductive_coupling": 0., "capacitive_coupling": 0.,
                 "frequency_stop_hz": 2e9, "frequency_points": 257, "reference_impedance_ohm": 50.}
    nodes = []
    for identity, channel, planes in (("A", leaf, ["input0", "input1", "a-joint0", "a-joint1"]),
                                     ("connector", connector, ["a-joint0", "a-joint1", "b-joint0", "b-joint1"]),
                                     ("B", leaf, ["b-joint0", "b-joint1", "output0", "output1"])):
        nodes.append({"id": identity, "owner_id": identity, "channel": channel,
                      "model_sha256": model_digest(channel), "reference_planes": planes})
    graph = {"kind": "network_graph", "reference_impedance_ohm": 50., "nodes": nodes,
             "connections": [{"a": {"node_id": a, "port": 2 + port}, "b": {"node_id": b, "port": port}}
                             for a, b in (("A", "connector"), ("connector", "B")) for port in (0, 1)],
             "external_ports": [{"id": f"{identity}-{port}", "node_id": identity, "port": port}
                                for identity, ports in (("A", (0, 1)), ("B", (2, 3))) for port in ports]}
    total, evidence = build_network_graph(graph)
    loaded = analyze_crosstalk(total, **model["crosstalk_model"])
    report = {"status": "executed", "elapsed_s": time.perf_counter() - begin,
              "source_metadata": design["metadata"], "extraction_geometry_digest": extraction["geometry_digest"],
              "cross_section": extraction["cross_section"], "graph_evidence": evidence,
              "maximum_singular_value": float(np.linalg.svd(total.parameters, compute_uv=False).max()),
              "reciprocity_max_error": float(np.abs(total.parameters - total.parameters.transpose(0, 2, 1)).max()),
              "loaded_time_domain": loaded["time_domain"], "production_qualified": False,
              "scope": "Two occurrences of actual pinned ESP32 0.7874 mm clipped ERXD0/ERXD1 overlap with authored synthetic connector. No complete routes, connector extraction or spatial inter-board field interaction."}
    for name, value in (("source-slice.json", design), ("extraction.json", extraction), ("graph.json", graph),
                        ("loaded-crosstalk.json", loaded), ("report.json", report)):
        (output / name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    (output / "graph.s4p").write_text(touchstone_text(total.frequencies_hz, total.parameters, 50.), encoding="ascii")
    print(json.dumps({"status": report["status"], "elapsed_s": report["elapsed_s"],
                      "cross_section_change": extraction["cross_section"]["latest_relative_matrix_change"],
                      "maximum_singular_value": report["maximum_singular_value"],
                      "reciprocity_max_error": report["reciprocity_max_error"],
                      "time_domain_status": loaded["time_domain"]["status"]}, indent=2))


if __name__ == "__main__":
    main()
