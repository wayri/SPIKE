#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Yawar Badri
"""Reproducible, bounded PI examples on the original SPIKE reference board.

The checks establish import, execution, invariants, and selected analytical
comparisons. They do not establish measured-board correlation or signoff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from python.spike_core.batch_report import normalize_pi_batch_report
from python.spike_core.benchmark_pdn import run_pdn_two_port_loading_benchmark
from python.spike_core.cli import _html_batch_report, _html_report
from python.spike_core.kicad_importer import import_kicad_design
from python.spike_core.peec_plugin import native_available
from python.spike_core import peec_plugin
from python.spike_core.service import handle, validate_design

BOARD = Path(__file__).with_name("spike-pi-reference.kicad_pcb")
BOARD_RELATIVE = "examples/pi/reference_board/spike-pi-reference.kicad_pcb"
MESH = {"target_size_mm": 5.0, "zone_cell_mm": 5.0, "max_zone_cells": 1000, "max_conductors": 2000}
FREQUENCIES_HZ = (1e3, 1e5, 3)


def case(name: str, passed: bool, level: str, evidence: dict, note: str) -> dict:
    return {"name": name, "status": "passed" if passed else "failed", "verification_level": level,
            "evidence": evidence, "scope": note}


def request(method: str, params: dict) -> dict:
    response = handle({"method": method, "params": params})
    if not response.get("ok"):
        raise RuntimeError(f"{method}: {response.get('error', 'worker request failed')}")
    return response["result"]


def spec(net: str, mode: str, source: tuple[float, float], load: tuple[float, float]) -> dict:
    result = {
        "analysis_id": f"reference-{net.lower()}-{mode}", "mode": mode, "net_names": [net],
        "sources": [{"id": "source", "position_mm": list(source), "layer": "F.Cu", "voltage_v": 1.0}],
        "loads": [{"id": "load", "position_mm": list(load), "layer": "F.Cu", "current_a": 0.1}],
        "mesh": dict(MESH),
    }
    if mode == "ac":
        result.update({"solver_id": "spike.peec_2_5d", "formulation": "peec_2_5d",
                       "frequency_start_hz": FREQUENCIES_HZ[0], "frequency_stop_hz": FREQUENCIES_HZ[1],
                       "frequency_points": FREQUENCIES_HZ[2]})
    return result


def pad_id(design: dict, net: str, x: float) -> str:
    matches = [p["id"] for p in design["pads"] if p["net_name"] == net and tuple(p["at"]) == (float(x), 10.0)]
    if len(matches) != 1:
        raise ValueError(f"Expected one {net} pad at x={x} mm; got {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the bounded JSON evidence here")
    parser.add_argument("--html-dir", type=Path, help="Also write portable PI HTML reports")
    args = parser.parse_args()
    if not native_available():
        parser.error("The native PEEC extension is required for the AC and PDN examples; build or install it first.")

    design_obj = import_kicad_design(str(BOARD))
    design = design_obj.to_dict()
    design["source_path"] = BOARD_RELATIVE
    checks: list[dict] = []
    counts = {key: len(getattr(design_obj, key)) for key in ("nets", "tracks", "vias", "pads", "zones", "components", "stackup")}
    validation = validate_design(design_obj)
    checks.append(case("kicad_import_and_design", validation["valid"] and counts == {
        "nets": 4, "tracks": 6, "vias": 2, "pads": 12, "zones": 2, "components": 8, "stackup": 3,
    }, "structural", {"counts": counts, "valid": validation["valid"]},
        "Original synthetic KiCad file; exact object census and importer validation."))

    preflight_spec = spec("VLOAD", "dc", (22, 10), (40, 10))
    preflight = request("preflight_analysis", {"design": design, "spec": preflight_spec})
    preview = request("preview_mesh", {"design": design, "spec": preflight_spec})
    checks.append(case("preflight_and_hybrid_mesh", bool(preflight.get("can_solve")) and
                       preview.get("contract") == "spike/mesh/v3" and
                       int(preview.get("cell_count", 0)) > 0 and
                       int(preview.get("branch_count", 0)) > 0,
                       "structural", {"can_solve": preflight.get("can_solve"),
                                      "preview_contract": preview.get("contract"),
                                      "cell_count": preview.get("cell_count"),
                                      "branch_count": preview.get("branch_count")},
                       "Trace, pad, filled zone, and plated-via geometry is admitted to the PI mesh."))

    runs: dict[str, dict] = {}
    cases = [
        ("vin_dc", "VIN", "dc", (5, 10), (20, 10)),
        ("vload_dc", "VLOAD", "dc", (22, 10), (40, 10)),
        ("vaux_dc", "VAUX", "dc", (5, 18), (40, 18)),
        ("vin_ac", "VIN", "ac", (5, 10), (20, 10)),
        ("vload_ac", "VLOAD", "ac", (22, 10), (40, 10)),
        ("vaux_ac", "VAUX", "ac", (5, 18), (40, 18)),
    ]
    for name, net, mode, source, load in cases:
        run_spec = spec(net, mode, source, load)
        if name == "vload_ac":
            run_spec["options"] = {"pdn_candidate_ports": [
                {"id": "C2-placed", "position_mm": [38, 10], "layer": "F.Cu", "net": "VLOAD", "endpoint_reviewed": True},
                {"id": "C3-dnp", "position_mm": [27, 10], "layer": "F.Cu", "net": "VLOAD", "endpoint_reviewed": True},
            ]}
        result = request("run_analysis", {"design": design, "spec": run_spec})
        runs[name] = result
        geometry = result.get("summary", {}).get("geometry_counts", {})
        parasitics = result.get("networks", {}).get("parasitics", [])
        samples = [point for network in parasitics for point in network.get("impedance", [])]
        passive_samples = all(math.isfinite(float(point["resistance_ohm"])) and
                              float(point["resistance_ohm"]) >= -1e-10 for point in samples)
        passed = result.get("status") == "completed" and result.get("model_status") == "approximate"
        if mode == "ac":
            passed = passed and native_available() and len(samples) == 3 and passive_samples
        if name == "vload_dc" or name == "vload_ac":
            passed = passed and all(geometry.get(kind, 0) >= count for kind, count in
                                    {"track": 3, "zone": 1, "via": 2, "pad": 4}.items())
        checks.append(case(name, passed, "execution_and_invariants",
                           {"status": result.get("status"), "model_status": result.get("model_status"),
                            "geometry_counts": geometry, "ac_samples": len(samples),
                            "error_codes": [issue.get("code") for issue in result.get("issues", []) if issue.get("severity") == "error"]},
                           "Board-derived result; an approximate model, not measured accuracy evidence."))

    # Independent closed-form conductor resistance; pad attachments make the
    # complete result slightly larger, so retain an explicit 2% tolerance.
    copper_sigma_s_m = 5.8e7
    analytic_ohm = 0.035 / (copper_sigma_s_m * 0.0008 * 0.000035)
    vaux_summary = runs["vaux_dc"]["summary"]
    solved_ohm = float(vaux_summary["max_load_voltage_drop_v"]) / 0.1
    relative_error = abs(solved_ohm - analytic_ohm) / analytic_ohm
    checks.append(case("vaux_dc_closed_form", relative_error <= 0.02, "analytical_reference",
                       {"expected_ohm": analytic_ohm, "computed_ohm": solved_ohm,
                        "relative_error": relative_error, "tolerance": 0.02},
                       "R=L/(sigma*w*t) for a 35 mm x 0.8 mm x 35 um straight copper trace; pads add contact geometry."))

    loss = float(vaux_summary["total_copper_loss_w"])
    expected_loss = 0.1 * float(vaux_summary["max_load_voltage_drop_v"])
    loss_error = abs(loss - expected_loss) / max(loss, expected_loss, 1e-30)
    checks.append(case("dc_power_balance", loss_error <= 0.01, "conservation",
                       {"copper_loss_w": loss, "current_times_load_drop_w": expected_loss,
                        "relative_error": loss_error, "tolerance": 0.01},
                       "Passive single-net DC path with one 0.1 A load."))

    convergence: dict[str, dict] = {}
    for net, source, load in (("VAUX", (5, 18), (40, 18)), ("VLOAD", (22, 10), (40, 10))):
        conv = request("mesh_convergence", {"design": design, "spec": spec(net, "dc", source, load),
                                            "options": {"levels": [2.0, 1.0, 0.5]}})
        convergence[net] = conv
        checks.append(case(f"{net.lower()}_dc_convergence", conv.get("status") == "passed", "mesh_refinement",
                           {"status": conv.get("status"), "level_count": len(conv.get("levels", []))},
                           "Three ordered refinement levels under the solver's unchanged required tolerances."))

    path = {"contract": "spike/pi-path/v1", "id": "vin-r1-vload", "label": "VIN through R1 to VLOAD",
            "source_terminal": {"net": "VIN", "pad_id": pad_id(design, "VIN", 5)},
            "load_terminal": {"net": "VLOAD", "pad_id": pad_id(design, "VLOAD", 40)},
            "segments": [{"id": "vin", "net": "VIN"}, {"id": "vload", "net": "VLOAD"}],
            "transitions": [{"id": "r1", "component_ref": "R1", "from_segment_id": "vin",
                             "to_segment_id": "vload", "input_pad_id": pad_id(design, "VIN", 20),
                             "output_pad_id": pad_id(design, "VLOAD", 22),
                             "model": {"primitive": "resistor", "connection_resistance_ohm": 0.1,
                                       "model_ref": "fixture:R1"}}]}
    path_validation = request("validate_pi_path", {"design": design, "path": path, "mode": "ac"})
    extraction = {"analysis_id": "reference-board-two-rail-peec", "model_status": "approximate",
                  "networks": {"parasitics": runs["vin_ac"]["networks"]["parasitics"] +
                               runs["vload_ac"]["networks"]["parasitics"]}}
    path_spec = {"analysis_id": "reference-series-ac", "mode": "ac", "net_names": ["VIN", "VLOAD"],
                 "sources": [{"id": "source", "net": "VIN", "voltage_v": 1.0, "ac_magnitude_v": 1.0}],
                 "loads": [{"id": "load", "net": "VLOAD", "current_a": 0.001, "ac_magnitude_a": 0.001}],
                 "return_path": {"net": "GND", "circuit_node": "0"},
                 "frequency_start_hz": 1e3, "frequency_stop_hz": 1e5, "frequency_points": 3,
                 "options": {"pi_path": path}}
    mappings = [{"segment_id": "vin", "network_index": 0, "from_pad_id": pad_id(design, "VIN", 5),
                 "to_pad_id": pad_id(design, "VIN", 20), "endpoint_reviewed": True},
                {"segment_id": "vload", "network_index": 1, "from_pad_id": pad_id(design, "VLOAD", 22),
                 "to_pad_id": pad_id(design, "VLOAD", 40), "endpoint_reviewed": True}]
    path_params = {"design": design, "spec": path_spec, "extraction_result": extraction,
                   "segment_mappings": mappings}
    compiled = request("compile_pi_path_native_mna", path_params)
    series = request("run_pi_path_native_mna", path_params)
    transition_r = [float(item["resistance_ohm"]) for item in compiled.get("request", {}).get("elements", [])
                    if item.get("id") == "X_r1:R"]
    residual = float(series.get("analysis_result", {}).get("summary", {}).get("relative_residual_max", math.inf))
    checks.append(case("reviewed_series_path_ac", path_validation.get("can_execute") is True and
                       compiled.get("status") == "ready" and series.get("status") == "completed" and
                       transition_r == [0.1] and residual < 1e-9, "reviewed_circuit_and_residual",
                       {"validation": path_validation.get("can_execute"), "compile": compiled.get("status"),
                        "run": series.get("status"), "series_resistance_ohm": transition_r,
                        "relative_residual_max": residual},
                       "Actual board-derived PEEC rail networks joined only at explicit R1 pads; no spatial circuit field is inferred."))

    multiports = runs["vload_ac"].get("networks", {}).get("pdn_multiports", [])
    candidates_valid = len(multiports) == 1 and {p.get("id") for p in multiports[0].get("ports", [])} == {
        "load", "C2-placed", "C3-dnp"}
    checks.append(case("pdn_board_multiport", candidates_valid, "board_extraction_invariants",
                       {"port_ids": [p.get("id") for m in multiports for p in m.get("ports", [])]},
                       "One observation port and two reviewed capacitor sites on the synthetic VLOAD rail."))
    library = [{"id": "C47u", "capacitance_f": 47e-6, "esr_ohm": 8e-3, "esl_h": 0.6e-9,
                "min_count": 1, "max_count": 1, "unit_cost": 0.25, "voltage_rating_v": 10,
                "ripple_current_rating_a": 1, "model_status": "approximate"}]
    optimized = request("pdn_optimize", {"result": runs["vload_ac"], "target_ohm": 0.05,
                                          "net": "VLOAD", "capacitor_library": library,
                                          "constraints": {"max_total_count": 1, "operating_voltage_v": 1,
                                                          "voltage_derating": 0.8, "required_ripple_current_a": 0.1}})
    rankings = {item["assignments"][0]["port_id"]: float(item["worst_target_ratio"])
                for item in optimized.get("recommendations", []) if len(item.get("assignments", [])) == 1}
    checks.append(case("placed_vs_dnp_cap_sensitivity", optimized.get("search_status") == "exhaustive" and
                       optimized.get("model_status") == "approximate" and
                       set(rankings) == {"C2-placed", "C3-dnp"} and
                       rankings["C3-dnp"] < rankings["C2-placed"], "bounded_sensitivity",
                       {"search_status": optimized.get("search_status"), "source_model_status": optimized.get("source_model_status"),
                        "worst_target_ratios": rankings, "target_ohm": 0.05},
                       "Equal nominal 47 uF/8 mOhm/0.6 nH parts at C2 (placed) and C3 (DNP); ranking is model sensitivity, not an operating-board optimum."))

    reference = run_pdn_two_port_loading_benchmark(lambda *a: None,
                                                    lambda name, status, actual, expected, error, tolerance, units, detail:
                                                    {"name": name, "status": status, "error": error,
                                                     "tolerance": tolerance, "units": units, "detail": detail})
    checks.append(case("pdn_loading_independent_nodal_reference", reference["status"] == "passed",
                       "analytical_reference", {"relative_error": reference["error"],
                                                "tolerance": reference["tolerance"]},
                       "17-frequency two-node nodal re-solve validates capacitor loading algebra, not PCB extraction accuracy."))

    batch_jobs = (("vin_dc", "VIN"), ("vaux_dc", "VAUX"), ("vload_ac", "VLOAD"))
    batch = {"contract": "spike/analysis-batch-result/v1", "status": "completed",
             "results": [{"index": index, "id": name,
                          "result": {**runs[name], "summary": {**runs[name]["summary"], "net_names": [net]}}}
                         for index, (name, net) in enumerate(batch_jobs)]}
    batch_report = normalize_pi_batch_report(batch)
    batch_report["totals"] = {key: value for key, value in batch_report["totals"].items()
                              if key in {"requested", "completed", "blocked", "failed", "cancelled",
                                         "not_run", "dc_jobs", "ac_jobs", "total_power_loss_w", "issue_count"}}
    checks.append(case("multinet_batch_and_portable_report", batch_report.get("status") == "completed" and
                       len(batch_report.get("jobs", [])) == 3 and
                       {net for job in batch_report.get("jobs", []) for net in job.get("nets", [])}
                       == {"VIN", "VAUX", "VLOAD"},
                       "result_contract", {"status": batch_report.get("status"),
                                           "job_count": len(batch_report.get("jobs", [])),
                                           "modes": [item.get("mode") for item in batch_report.get("jobs", [])]},
                       "Repeated independent net requests compiled into a versioned PI-only batch report."))

    report = {
        "contract": "spike/pi-reference-evidence/v1", "board": BOARD_RELATIVE,
        "board_sha256": hashlib.sha256(BOARD.read_bytes()).hexdigest(),
        "native_peec_sha256": hashlib.sha256(Path(peec_plugin.native.__file__).read_bytes()).hexdigest(),
        "solver_ids": sorted({str(runs[name].get("provenance", {}).get("solver", "")) for name in runs}),
        "copyright": "Yawar Badri", "board_license": "MIT", "analysis_status": "approximate",
        "limits": [
            "Synthetic board and nominal copper/FR4/capacitor parameters; no measured hardware correlation.",
            "AC quasi-static PEEC results are approximate and retain their result-level validity limits.",
            "Placed-versus-DNP capacitor comparison assumes equal nominal parts and ideal common return reference.",
            "This example does not resolve Marble or MODULAR-BUS-NIB AC passivity and convergence failures.",
            "A knowledgeable human must review numerical models before release promotion.",
        ],
        "checks": checks,
        "status": "passed" if all(item["status"] == "passed" for item in checks) else "failed",
        "release_validated": False,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    if args.html_dir:
        args.html_dir.mkdir(parents=True, exist_ok=True)
        (args.html_dir / "vload-dc.html").write_text(_html_report(runs["vload_dc"]), encoding="utf-8")
        (args.html_dir / "vload-ac.html").write_text(_html_report(runs["vload_ac"]), encoding="utf-8")
        (args.html_dir / "batch.html").write_text(_html_batch_report(batch_report), encoding="utf-8")
    print(f"SPIKE PI reference: {sum(x['status'] == 'passed' for x in checks)}/{len(checks)} checks passed; release_validated=false")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
