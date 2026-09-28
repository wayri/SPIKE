# SPDX-License-Identifier: Apache-2.0
"""Local pinned-board connector/placement smoke; electrical values are synthetic."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.design_ir_v2 import DesignIRV2, AssemblyIRV1
from python.spike_core.assembly_frames import IDENTITY
from python.spike_core.harness_authoring import discover_connectors, plan_harnesses
from python.spike_core.harness_pi import run_harness_pi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("board", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output must be a new evidence file.")
    design = DesignIRV2.from_v1(import_kicad_design(str(args.board))).to_dict()
    rotated = [0, -1, 0, 300, 1, 0, 0, 0, 0, 0, 1, 25, 0, 0, 0, 1]
    assembly = {"assembly_id": "marble-harness-smoke", "name": "Two placed occurrences",
                "boards": [{"id": "a", "design_id": "d", "frame": {"frame_id": "a", "transform": IDENTITY}},
                           {"id": "b", "design_id": "d", "frame": {"frame_id": "b", "transform": rotated}}]}
    connectors = discover_connectors(AssemblyIRV1.from_dict(assembly), {"d": design})
    a = next(c for c in connectors.values() if c["board_id"] == "a" and len(c["pins"]) >= 2)
    pins = sorted(a["pins"])[:2]
    reference = a["connector_id"]
    plan = plan_harnesses({"assembly": assembly, "designs": {"d": design}, "pairs": [
        {"endpoint_a": f"a::{reference}", "endpoint_b": f"b::{reference}", "pin_map": dict(zip(pins, pins))}]})
    assert len(plan["harnesses"]) == 1
    endpoint = lambda c, p: {"connector": c, "pin": p}
    harness = {"contract": "spike/harness/v1", "id": "marble-authored-loop", "name": "Synthetic loop on real pin identities",
               "connectors": [{"id": c, "board_binding": {"board_id": c, "connector_id": reference},
                               "pins": [{"id": p} for p in pins]} for c in ("a", "b")],
               "wires": [{"id": str(i), "from": endpoint("a", p), "to": endpoint("b", p),
                          "electrical": {"resistance_ohm": .1}} for i, p in enumerate(pins)]}
    result = run_harness_pi({"contract": "spike/harness-pi-request/v1", "harness": harness,
                            "ground": endpoint("a", pins[1]), "terminals": [
        {"id": "supply", "type": "voltage_source", "positive": endpoint("a", pins[0]), "negative": endpoint("a", pins[1]), "value": 12},
        {"id": "load", "type": "current_load", "positive": endpoint("b", pins[0]), "negative": endpoint("b", pins[1]), "value": 2}]})
    load = next(c for c in result["connections"] if c["id"] == "load")
    assert abs(load["voltage_v"] - 11.6) < 1e-9
    evidence = {"status": "passed", "source_sha256": hashlib.sha256(args.board.read_bytes()).hexdigest(),
                "source": str(args.board.resolve()), "board_occurrences": 2, "connector": reference, "pins": pins,
                "harness_length_mm": plan["harnesses"][0]["length_mm"], "load_voltage_v": load["voltage_v"],
                "qualification": "Connector identity/rotated placement plus synthetic lumped DC smoke only; no Marble copper, power-rating or measured validation."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
