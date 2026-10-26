# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Replay a retained EMerge result through explicitly declared circuit boundaries.

This is not a fresh EMerge solve, live-board authentication, field calibration,
or a PCB thermal prediction. Refuses overwriting retained evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from extensions.emerge_suite.cosimulation import prepare_cosimulation_source
from python.spike_core.solvers.execution.coupling.em_network_ac import REQUEST_CONTRACT, WAVE_CONVENTION, solve_em_network_ac


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory")
    args = parser.parse_args()
    fixture = ROOT / "examples/emerge/gui_workflow/patch_admitted_result.json"
    content = fixture.read_bytes()
    raw = json.loads(content)
    provenance = raw["provenance"]
    ports = raw["networks"]["s_parameters"]["ports"]
    packet = prepare_cosimulation_source(raw,
        {"design_id": provenance["design_id"], "digest_sha256": provenance["design_digest_sha256"]},
        expected_case_sha256=provenance["board_case_sha256"],
        expected_script_sha256=provenance["generated_script_sha256"],
        port_bindings={p: {"positive_node": "signal-"+str(i), "negative_node": "0",
                           "reference_plane": "retained-source-port-plane-no-shift"}
                       for i, p in enumerate(ports)}, wave_convention=WAVE_CONVENTION)
    request = {"contract": REQUEST_CONTRACT, "source": packet["network_source"],
        "wave_convention": WAVE_CONVENTION,
        "boundaries": [{p: {"voltage_v": [2. if i == 0 else 0., 0.], "impedance_ohm": [50., 0.]}
                        for i, p in enumerate(ports)} for _ in packet["network_source"]["frequencies_hz"]]}
    result = solve_em_network_ac(request)
    args.output.mkdir(parents=True, exist_ok=False)
    records = {"packet.json": packet, "request.json": request, "result.json": result}
    hashes = {}
    for name, record in records.items():
        data = (json.dumps(record, indent=2, allow_nan=False)+"\n").encode()
        (args.output/name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    manifest = {"fixture": str(fixture.relative_to(ROOT)), "fixture_sha256": hashlib.sha256(content).hexdigest(),
        "artifact_sha256": hashes, "fresh_em_solve": False, "source_model_status": raw["model_status"],
        "source_files_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
            "extensions/emerge_suite/cosimulation.py", "extensions/emerge_suite/normalize.py",
            "python/spike_core/solvers/execution/coupling/em_network_ac.py", "python/spike_core/solvers/signal_integrity/networks/sparameter_sampling.py")},
        "assumptions": ["Offline retained-result replay; binding hashes self-pinned from retained provenance",
                        "Explicit new 2 V RMS source and 50 ohm series/termination circuit",
                        "Declared RMS power waves, not independently calibrated field amplitude",
                        "No EM deficit deposited as thermal heat; no live SPICE engine execution"]}
    (args.output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"samples": len(result["samples"]), "source_status": raw["model_status"],
        "maximum_power_balance_error_w": max(x["power_balance_error_w"] for x in result["samples"]),
        "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
