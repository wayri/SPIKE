# SPDX-License-Identifier: Apache-2.0
"""Probe inert IBIS compilation and supplied-RLGC spatial SI across worker IPC.

This transport/resource check does not execute ngspice or qualify numerical
accuracy, fixture convergence, a vendor model, or a physical PCB extraction.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def verify_si_ibis_spatial_runtime(executable, request, *, resource_root=None):
    root = Path(resource_root) if resource_root is not None else ROOT
    fixtures = root / "examples" / "si"
    ibis = json.loads((fixtures / "ibis_driver_receiver" / "request.json").read_text(encoding="utf-8"))
    compiled = request(executable, "compile_ibis_behavioral", {"request": ibis})["result"]
    if (compiled.get("status") != "ready" or compiled.get("model_status") != "experimental"
            or compiled.get("production_qualified") is not False):
        raise RuntimeError("IBIS fixture compilation failed or lost its experimental status")
    if compiled.get("netlist_sha256") != sha256(compiled["netlist"].encode("ascii")).hexdigest():
        raise RuntimeError("IBIS generated deck digest is invalid")
    expected_request = sha256(json.dumps(ibis, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if compiled.get("request_sha256") != expected_request:
        raise RuntimeError("IBIS compilation lost exact request provenance")
    runtime = request(executable, "inspect_ibis_behavioral_runtime", {})["result"]
    if (runtime.get("executed") is not False or runtime.get("sandboxed") is not False
            or runtime.get("trusted_native_code_required") is not True
            or runtime.get("status") not in {"available", "unavailable"}):
        raise RuntimeError("IBIS runtime inspection lost inert/trusted-runtime semantics")
    setup = json.loads((fixtures / "spatial_crosstalk" / "setup.json").read_text(encoding="utf-8"))
    result = request(executable, "run_si_spatial_pair", setup)["result"]
    data, raw = result["data"], result["sourceResult"]
    context = result["context"]
    if (data.get("modelStatus") != "experimental" or data.get("status") != "completed_with_warnings"
            or data["sourceResult"]["modelScope"].get("extracted") is not False
            or not data["sourceResult"]["modelScope"].get("limitations")):
        raise RuntimeError("Spatial SI lost supplied-model status or limitations")
    design_digest = sha256(json.dumps(setup["design"], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if context["designDigest"] != design_digest or data["binding"]["sourceDesignDigest"] != design_digest:
        raise RuntimeError("Spatial SI lost current geometry provenance")
    if (data["binding"]["requestId"] != setup["request_id"]
            or data["sourceResult"]["inputDigest"] != raw["input_digest"]
            or data["frequenciesHz"] != [point["frequency_hz"] for point in raw["points"]]
            or len(data["traceSamples"]) != len(setup["pair_request"]["probes"])):
        raise RuntimeError("Spatial SI lost request, source or sample identity")
    nonzero = False
    for index, sample in enumerate(data["traceSamples"]):
        if (sample["segmentId"] != setup["victim_segment_id"]
                or sample["fraction"] != setup["pair_request"]["probes"][index]["fractional_position"]
                or len(sample["inducedVoltageV"]) != len(raw["points"])):
            raise RuntimeError("Spatial SI mapped a sample to the wrong stroke or position")
        for voltage, point in zip(sample["inducedVoltageV"], raw["points"]):
            original = point["probe_values"][index]["conductors"][1]["voltage_v"]
            expected = [original["real"], original["imag"]]
            if voltage != expected or not all(math.isfinite(value) for value in voltage):
                raise RuntimeError("Spatial SI differs from the returned raw victim-voltage samples")
            nonzero = nonzero or any(value != 0 for value in voltage)
    if not nonzero:
        raise RuntimeError("Spatial SI fixture unexpectedly returned only zero coupling")
    return {"status": "passed", "checks": ["inert_ibis_compilation", "runtime_identity_inspection",
            "geometry_digest", "raw_probe_mapping", "experimental_limits"],
            "ibis_netlist_sha256": compiled["netlist_sha256"], "runtime_status": runtime["status"],
            "spatial_samples": len(data["traceSamples"]), "frequencies": len(raw["points"]),
            "native_execution": "not_run", "production_qualified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, help="Frozen worker; default exercises the source service")
    parser.add_argument("--resource-root", type=Path, default=ROOT, help="Source/staged/installed resource root")
    args = parser.parse_args()
    if args.worker:
        from scripts.build_packaged_worker import _request
        request = _request
    else:
        from python.spike_core.service import handle

        def request(executable, method, params):
            response = handle({"id": "si-ibis-spatial-probe", "method": method, "params": params})
            if response.get("ok") is not True:
                raise RuntimeError(f"Source service rejected {method}: {response}")
            return response
    print(json.dumps(verify_si_ibis_spatial_runtime(args.worker, request, resource_root=args.resource_root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
