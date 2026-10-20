# SPDX-License-Identifier: Apache-2.0
"""Execute bounded native CHT examples and conservative interface handoffs.

Creates new evidence, never edits a prior report or claims release qualification.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.native_cht import run_native_cht, executable_path, REQUEST
from python.spike_core.coupled_surface_exchange import (
    coupled_surface_context_digest, transfer_coupled_surface_exchange)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def thermal_handoff(result):
    """Explicit analytic matching/split partition, not a CAD overlap inference."""
    interface = result["interfaces"]["bottom"]
    n, area = result["settings"]["n"], interface["face_area_m2"]
    geometry = {"source": result["provenance"]["request_sha256"], "plane": "y=0",
                "width": result["settings"]["length_m"], "span": result["settings"]["span_m"]}
    geometry_digest = hashlib.sha256(json.dumps(geometry, sort_keys=True).encode()).hexdigest()
    def patch(participant, faces):
        return {"participant_id": participant, "patch_id": "flat-interface",
                "geometry_digest": geometry_digest, "frame": {"id": "cavity-SI", "rank": 3,
                "handedness": "right"}, "faces": faces}
    request = {"contract": "spike/coupled-surface-exchange-request/v1",
        "transfer_id": "native-hot-solid-to-split-fluid-patch", "quantity": "heat_flux",
        "normal_relation": "opposite_outward_normals",
        "units": {"length": "m", "area": "m2", "source_intensive": "W/m2", "destination_integrated": "W"},
        "source_patch": patch("native-hot-solid", [{"id": f"s{i}", "area_m2": area} for i in range(n)]),
        "destination_patch": patch("supplied-split-thermal-interface", [
            {"id": f"d{i}-{half}", "area_m2": area/2} for i in range(n) for half in range(2)]),
        "overlaps": [{"source_face_id": f"s{i}", "destination_face_id": f"d{i}-{half}", "area_m2": area/2}
                     for i in range(n) for half in range(2)],
        "source_values": [{"face_id": f"s{i}", "value": q} for i, q in enumerate(interface["heat_flux_positive_y_w_m2"])],
        "destination_value_unit": "K", "destination_values": [
            {"face_id": f"d{i}-{half}", "value": t} for i, t in enumerate(interface["temperature_k"]) for half in range(2)]}
    request["context_digest"] = coupled_surface_context_digest(request)
    return request, transfer_coupled_surface_exchange(request)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("Choose a new output folder; existing evidence is never overwritten")
    output.mkdir(parents=True)
    sources = [Path(__file__).resolve(), *sorted((ROOT/"src/airflow").glob("*.cpp")),
        *sorted((ROOT/"src/airflow").glob("*.hpp")), ROOT/"src/airflow/CMakeLists.txt",
        ROOT/"python/spike_core/native_cht.py", ROOT/"python/spike_core/native_cht_result.py",
        ROOT/"python/spike_core/coupled_surface_exchange.py", ROOT/"python/spike_core/sparselizard_process.py",
        *sorted(Path(__file__).parent.glob("*.json"))]
    before = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    binary = executable_path()
    binary_hash = sha(binary)
    rows, checks = [], []
    def execute(name, request):
        dump(output/(name+".request.json"), request)
        result = run_native_cht(request)
        dump(output/(name+".result.json"), result)
        rows.append({"case": name, "status": result["status"],
            "raw_balance_w": result["diagnostics"].get("raw_energy_balance_w"),
            "relative_balance": result["diagnostics"]["balance_relative"],
            "input_sha256": sha(output/(name+".request.json")),
            "output_sha256": sha(output/(name+".result.json"))})
        checks.append({"case": name, "check": "discrete_convergence", "passed": result["status"] == "converged"})
        return result
    for name in ("native-cht-conduction", "native-cht-air-like", "native-cht-liquid-like"):
        request = json.loads((Path(__file__).parent/(name+".json")).read_text())
        result = execute(name, request)
        if name == "native-cht-conduction" and result["status"] == "converged":
            error = abs(result["diagnostics"]["hot_input_w"]-10/105)
            checks.append({"case": name, "check": "independent_series_resistance", "error_w": error,
                           "tolerance_w": 1e-9, "passed": error <= 1e-9})
        if result["status"] == "converged":
            mapped_request, mapped = thermal_handoff(result)
            dump(output/(name+".exchange.request.json"), mapped_request)
            dump(output/(name+".exchange.result.json"), mapped)
            balance = mapped["diagnostics"]["maximum_absolute_balance"]
            source = mapped["diagnostics"]["source_outward_integrated_total"]
            native_heat = result["diagnostics"]["interface_heat_flow_w"]["bottom"]
            checks.append({"case": name, "check": "native_interface_to_split_patch_conservation",
                "raw_balance_w": balance, "native_source_difference_w": source-native_heat,
                "passed": balance <= 1e-12*max(1., abs(source))
                    and abs(source-native_heat) <= 1e-12*max(1., abs(source))})
    heat = []
    for n in (8, 16, 32):
        result = execute(f"moving-refinement-{n}", {"contract": REQUEST, "n": n,
            "specific_heat_j_kgk": .1, "solid_conductivity_w_mk": .01})
        heat.append(result["diagnostics"].get("hot_input_w"))
    if all(value is not None for value in heat):
        coarse, fine = abs(heat[1]-heat[0]), abs(heat[2]-heat[1])
        checks.append({"case": "moving-refinement", "check": "decreasing_successive_heat_change",
            "coarse_change_w": coarse, "fine_change_w": fine, "passed": fine < coarse})
    after = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    stable = before == after and sha(binary) == binary_hash
    report = {"contract": "spike/internal-cfd-development-evidence/v1", "production_qualified": False,
        "status": "passed" if stable and all(c["passed"] for c in checks) else "failed",
        "source_stable": stable, "source_sha256": before, "executable_sha256": binary_hash,
        "python": sys.version, "platform": platform.platform(), "cases": rows, "checks": checks,
        "limits": ["Analytical and discrete/refinement checks only, not measured validation",
                   "Split-patch exchange does not execute a second thermal or structural solver",
                   "Air/liquid-like property values are illustrative constants, not certified material data",
                   "No turbulence, arbitrary geometry, rotor, compressible flow or FSI/flutter claim"]}
    dump(output/"report.json", report)
    print(json.dumps({"status": report["status"], "cases": len(rows), "checks": len(checks), "source_stable": stable}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
