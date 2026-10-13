# SPDX-License-Identifier: Apache-2.0
"""Run bounded thermal cooling comparisons with actual installed solvers.

The fixtures are original SPIKE fixtures.  No upstream solver example, mesh,
or reference result is copied.  Passing this script creates candidate numerical
evidence only; it never sets production qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.assembly_tetra_thermal import run_assembly_tetra_thermal
from python.spike_core.assembly_tetra_thermal_validation import validate_request
from python.spike_core.calculix_deck import compile_calculix_deck
from python.spike_core.calculix_runtime import probe_calculix_runtime, run_calculix_deck
from python.spike_core.openfoam_fan_fixture import build_fan_heated_fixture
from python.spike_core.openfoam_flow_energy_validation import read_numeric_history, validate_flow_energy
from python.spike_core.openfoam_multiregion_execution import (
    load_verified_runnable_case,
    run_multiregion_case,
)
from python.spike_core.openfoam_runtime import detect_openfoam_runtime
from tests.python.test_assembly_tetra_radiation import slab
from tests.python.test_assembly_tetra_thermal import contact_request


REPORT_CONTRACT = "spike/thermal-cooling-environment-validation/v1"
TEMPERATURE_ABSOLUTE_TOLERANCE_K = 1.0e-3
CONTACT_FLOW_RELATIVE_TOLERANCE = 1.0e-6
SOLID_ENERGY_RELATIVE_TOLERANCE = 1.0e-8
CFD_MASS_RELATIVE_TOLERANCE = 2.0e-7
CFD_FINAL_MASS_RELATIVE_TOLERANCE = 1.0e-8
CFD_ENERGY_RELATIVE_TOLERANCE = 1.0e-2
OPENFOAM_DIVISIONS = 2


def _digest_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _execution_identity(execution: dict[str, Any]) -> dict[str, Any]:
    runtime = execution["runtime"]
    return {
        "solver_version": execution["solver_version"],
        "executable_sha256": runtime["executable_sha256"],
        "input_sha256": execution["input_sha256"],
        "output_sha256": execution["output_sha256"],
        "log_sha256": execution["log_sha256"],
        "exit_code": execution["exit_code"],
        "solver_reported_finished": execution["solver_reported_finished"],
    }


def _relative_residual(numerator: float, *scales: float) -> float:
    return abs(numerator) / max(*(abs(value) for value in scales), 1.0e-30)


def run_established_solver_comparisons() -> dict[str, Any]:
    """Compare SPIKE with analytical fixtures and separately installed CCX."""
    runtime = probe_calculix_runtime()
    if not runtime["available"]:
        return {
            "status": "blocked",
            "passed": False,
            "runtime": runtime,
            "reason": "A completed CalculiX solve is required; discovery alone is not comparison evidence.",
        }

    cooling_request, imposed_heat_w = slab(2)
    cooling_internal = run_assembly_tetra_thermal(cooling_request)
    cooling_external_execution = run_calculix_deck(
        compile_calculix_deck(cooling_request), {"timeout_seconds": 30, "threads": 1}
    )
    cooling_internal_t = np.asarray(cooling_internal["node_temperatures_k"], dtype=float)
    cooling_external_t = np.asarray(cooling_external_execution["node_temperatures_k"], dtype=float)
    cooling_exact_t = np.asarray(
        [350.0 + imposed_heat_w / 2.0 * (1.0 - point[0]) for point in cooling_request["mesh"]["vertices"]],
        dtype=float,
    )
    heat_balance = cooling_internal["heat_balance"]
    heat_relative = _relative_residual(
        heat_balance["imbalance_w"],
        heat_balance["prescribed_flux_inward_w"],
        heat_balance["convection_outward_w"],
        heat_balance["radiation_outward_w"],
    )
    cooling = {
        "fixture": "original combined convection/diffuse-gray-radiation slab",
        "nodes": len(cooling_exact_t),
        "analytical_equation": "T(x)=350 + q/(2 W/m/K)*(1-x), q=10*(350-300)+0.8*sigma*(350^4-300^4) W/m2",
        "spike_maximum_absolute_error_k": float(np.max(np.abs(cooling_internal_t - cooling_exact_t))),
        "calculix_maximum_absolute_error_k": float(np.max(np.abs(cooling_external_t - cooling_exact_t))),
        "spike_calculix_maximum_absolute_difference_k": float(np.max(np.abs(cooling_internal_t - cooling_external_t))),
        "temperature_absolute_tolerance_k": TEMPERATURE_ABSOLUTE_TOLERANCE_K,
        "spike_heat_balance": heat_balance,
        "spike_heat_balance_relative_residual": heat_relative,
        "energy_relative_tolerance": SOLID_ENERGY_RELATIVE_TOLERANCE,
        "calculix_execution": _execution_identity(cooling_external_execution),
    }
    cooling["passed"] = bool(
        cooling["spike_maximum_absolute_error_k"] <= TEMPERATURE_ABSOLUTE_TOLERANCE_K
        and cooling["calculix_maximum_absolute_error_k"] <= TEMPERATURE_ABSOLUTE_TOLERANCE_K
        and cooling["spike_calculix_maximum_absolute_difference_k"] <= TEMPERATURE_ABSOLUTE_TOLERANCE_K
        and heat_relative <= SOLID_ENERGY_RELATIVE_TOLERANCE
    )

    contact = contact_request()
    contact_internal = run_assembly_tetra_thermal(contact)
    contact_external_execution = run_calculix_deck(
        compile_calculix_deck(contact), {"timeout_seconds": 30, "threads": 1}
    )
    contact_internal_t = np.asarray(contact_internal["node_temperatures_k"], dtype=float)
    contact_external_t = np.asarray(contact_external_execution["node_temperatures_k"], dtype=float)
    parsed = validate_request(contact)
    external_flows = []
    for contact_id, left, right, area, conductance in parsed["contacts"]:
        flow_w = float(area * conductance * np.mean(contact_external_t[list(left)] - contact_external_t[list(right)]))
        external_flows.append({"id": contact_id, "left_to_right_heat_w": flow_w})
    internal_by_id = {item["id"]: item["left_to_right_heat_w"] for item in contact_internal["contacts"]}
    flow_errors = [
        _relative_residual(item["left_to_right_heat_w"] - internal_by_id[item["id"]], item["left_to_right_heat_w"], internal_by_id[item["id"]])
        for item in external_flows
    ]
    interface = {
        "fixture": "original retained two-solid contact slab",
        "spike_calculix_maximum_absolute_difference_k": float(np.max(np.abs(contact_internal_t - contact_external_t))),
        "temperature_absolute_tolerance_k": TEMPERATURE_ABSOLUTE_TOLERANCE_K,
        "spike_interface_heat_flow": contact_internal["contacts"],
        "calculix_interface_heat_flow": external_flows,
        "maximum_relative_interface_heat_flow_difference": max(flow_errors, default=0.0),
        "interface_heat_flow_relative_tolerance": CONTACT_FLOW_RELATIVE_TOLERANCE,
        "calculix_execution": _execution_identity(contact_external_execution),
    }
    interface["passed"] = bool(
        interface["spike_calculix_maximum_absolute_difference_k"] <= TEMPERATURE_ABSOLUTE_TOLERANCE_K
        and interface["maximum_relative_interface_heat_flow_difference"] <= CONTACT_FLOW_RELATIVE_TOLERANCE
    )
    return {
        "status": "passed" if cooling["passed"] and interface["passed"] else "failed",
        "passed": bool(cooling["passed"] and interface["passed"]),
        "runtime": runtime,
        "cooling_environment": cooling,
        "solid_interface": interface,
    }


def _single_history(case_dir: Path, region: str, name: str) -> tuple[np.ndarray, str, str]:
    paths = list((case_dir / "postProcessing" / region / name).glob("*/surfaceFieldValue.dat"))
    if len(paths) != 1 or not paths[0].resolve().is_relative_to(case_dir.resolve()):
        raise ValueError(f"Expected one bounded {name} history.")
    values, digest = read_numeric_history(paths[0], 2)
    return values, digest, paths[0].relative_to(case_dir).as_posix()


def evaluate_openfoam_mass_balance(case_dir: str | Path, *, expected_mass_flow_kg_s: float) -> dict[str, Any]:
    root = Path(case_dir).resolve(strict=True)
    inlet, inlet_digest, inlet_path = _single_history(root, "air", "spikeMassFlux_air_fan_in")
    outlet, outlet_digest, outlet_path = _single_history(root, "air", "spikeMassFlux_air_exhaust")
    if not np.array_equal(inlet[:, 0], outlet[:, 0]):
        raise ValueError("OpenFOAM inlet and outlet mass histories are not aligned.")
    if not np.all(inlet[:, 1] < 0) or not np.all(outlet[:, 1] > 0):
        raise ValueError("OpenFOAM fan fixture mass-flow signs are invalid.")
    relative = np.abs(inlet[:, 1] + outlet[:, 1]) / np.maximum(np.abs(inlet[:, 1]), 1.0e-30)
    prescribed = np.abs(np.abs(inlet[:, 1]) - expected_mass_flow_kg_s) / expected_mass_flow_kg_s
    result = {
        "status": "evaluated",
        "samples": len(relative),
        "expected_inlet_mass_flow_kg_s": expected_mass_flow_kg_s,
        "maximum_relative_mass_mismatch": float(np.max(relative)),
        "final_relative_mass_mismatch": float(relative[-1]),
        "maximum_relative_prescribed_inlet_error": float(np.max(prescribed)),
        "relative_tolerance": CFD_MASS_RELATIVE_TOLERANCE,
        "final_relative_tolerance": CFD_FINAL_MASS_RELATIVE_TOLERANCE,
        "history_sha256": {inlet_path: inlet_digest, outlet_path: outlet_digest},
    }
    result["passed"] = bool(
        result["maximum_relative_mass_mismatch"] <= CFD_MASS_RELATIVE_TOLERANCE
        and result["final_relative_mass_mismatch"] <= CFD_FINAL_MASS_RELATIVE_TOLERANCE
        and result["maximum_relative_prescribed_inlet_error"] <= CFD_FINAL_MASS_RELATIVE_TOLERANCE
    )
    return result


def run_openfoam_cht(artifacts: str | Path) -> dict[str, Any]:
    runtime = detect_openfoam_runtime()
    if not runtime["available"] or str(runtime.get("version")) != "2606":
        return {
            "status": "blocked",
            "passed": False,
            "runtime": runtime,
            "reason": "An executable OpenFOAM v2606 runtime is required; saved candidate summaries are not substituted.",
        }
    root = Path(artifacts).resolve()
    if root.exists():
        if any(root.iterdir()):
            raise ValueError("OpenFOAM artifact directory must not already contain files.")
    else:
        root.mkdir(parents=True)
    fixture = build_fan_heated_fixture(
        root,
        divisions=OPENFOAM_DIVISIONS,
        board_count=1,
        delta_t_s=0.001,
        end_time_s=0.01,
        write_interval_steps=10,
    )
    result = run_multiregion_case(root / "case", timeout_s=180, runtime=runtime)
    _, manifest = load_verified_runnable_case(root / "case")
    commands = result.get("runtime_probe", {}).get("commands", {})
    execution = {
        "status": result.get("status"),
        "manifest_digest": manifest["manifest_digest"],
        "field_export_sha256": result.get("provenance", {}).get("field_export_sha256"),
        "summary": result.get("summary"),
        "runtime_commands": {
            name: {key: item[key] for key in ("available", "return_code", "reason") if key in item}
            for name, item in commands.items()
        },
    }
    if result.get("status") != "completed":
        return {
            "status": "failed",
            "passed": False,
            "runtime": runtime,
            "execution": execution,
            "reason": result.get("message", "OpenFOAM execution did not complete."),
        }
    expected_mass_flow = fixture["request"]["materials"][1]["density_kg_m3"] * fixture["request"]["fans"][0]["flow_rate_m3_s"]
    mass = evaluate_openfoam_mass_balance(root / "case", expected_mass_flow_kg_s=expected_mass_flow)
    energy = validate_flow_energy(
        root / "case",
        dpdt_enabled=True,
        orthogonal_constant_k=True,
        relative_tolerance=CFD_ENERGY_RELATIVE_TOLERANCE,
    )
    interface = {
        "status": "not_evaluated",
        "passed": False,
        "reason": (
            "The current field export contains cell-centred molecular conductive heat-flux vectors, "
            "but no signed patch-integrated heat-flow history on both sides of the conjugate interface."
        ),
        "required_next_evidence": "Hash-bound paired patch heat-flow histories with sign and closure checks.",
    }
    return {
        "status": "passed" if mass["passed"] and energy["passed"] else "failed",
        "passed": bool(mass["passed"] and energy["passed"]),
        "runtime": runtime,
        "fixture": {
            "contract": fixture["contract"],
            "divisions": OPENFOAM_DIVISIONS,
            "cells_per_region": OPENFOAM_DIVISIONS ** 3,
            "time_step_s": 0.001,
            "end_time_s": 0.01,
            "fan_volume_flow_m3_s": fixture["request"]["fans"][0]["flow_rate_m3_s"],
            "source_power_w": sum(item["power_w"] for item in fixture["request"]["heat_sources"]),
        },
        "execution": execution,
        "mass_balance": mass,
        "energy_balance": energy,
        "conjugate_interface_heat_flow": interface,
        "scope": "Short deterministic laminar CHT execution smoke check; no mesh/time convergence or measured airflow correlation.",
    }


def _source_identity() -> dict[str, str]:
    paths = [
        Path(__file__),
        ROOT / "python/spike_core/assembly_tetra_thermal.py",
        ROOT / "python/spike_core/calculix_deck.py",
        ROOT / "python/spike_core/calculix_runtime.py",
        ROOT / "python/spike_core/openfoam_fan_fixture.py",
        ROOT / "python/spike_core/openfoam_flow_energy_validation.py",
        ROOT / "python/spike_core/openfoam_multiregion_execution.py",
        ROOT / "tests/python/test_assembly_tetra_radiation.py",
        ROOT / "tests/python/test_assembly_tetra_thermal.py",
    ]
    return {path.relative_to(ROOT).as_posix(): _digest_bytes(path) for path in paths}


def run_validation(artifacts: str | Path, *, include_openfoam: bool = True) -> dict[str, Any]:
    before = _source_identity()
    comparisons = run_established_solver_comparisons()
    cfd = run_openfoam_cht(artifacts) if include_openfoam else {
        "status": "not_requested", "passed": False,
        "reason": "OpenFOAM execution was explicitly omitted from this invocation.",
    }
    after = _source_identity()
    statuses = [comparisons["status"], cfd["status"]]
    overall = "passed" if statuses == ["passed", "passed"] else "failed" if "failed" in statuses else "blocked"
    return {
        "contract": REPORT_CONTRACT,
        "status": overall,
        "model_status": "experimental_candidate_evidence",
        "production_qualified": False,
        "tolerances": {
            "temperature_absolute_k": TEMPERATURE_ABSOLUTE_TOLERANCE_K,
            "solid_interface_heat_flow_relative": CONTACT_FLOW_RELATIVE_TOLERANCE,
            "solid_energy_relative": SOLID_ENERGY_RELATIVE_TOLERANCE,
            "cfd_mass_relative": CFD_MASS_RELATIVE_TOLERANCE,
            "cfd_final_mass_relative": CFD_FINAL_MASS_RELATIVE_TOLERANCE,
            "cfd_energy_relative": CFD_ENERGY_RELATIVE_TOLERANCE,
        },
        "established_solver_comparisons": comparisons,
        "openfoam_conjugate_airflow": cfd,
        "source_identity": before,
        "sources_unchanged_during_run": before == after,
        "qualification": {
            "production_qualified": False,
            "reason": "Authored numerical checks cannot grant qualification; independent review, representative geometry, convergence, and measured correlation remain required.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--skip-openfoam", action="store_true", help="Run only solid/CalculiX comparisons and report CFD as not requested.")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; validation evidence is write-once.")
    if args.artifacts.exists() and any(args.artifacts.iterdir()):
        parser.error("Artifacts directory must be absent or empty.")
    report = run_validation(args.artifacts, include_openfoam=not args.skip_openfoam)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": report["status"], "output": str(args.output), "artifacts": str(args.artifacts)}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
