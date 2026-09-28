# SPDX-License-Identifier: Apache-2.0
"""Executable openEMS adapter benchmarks with narrow, explicit validation scope."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Iterable

from python.spike_core.contracts import AnalysisSpec, DesignIR
from .engine import prepare_openems_case, run_openems_case
from .openems_validation import FAR_FIELD_REQUEST_CONTRACT


REFERENCE_URL = "https://docs.openems.de/python/openEMS/Tutorials/Simple_Patch_Antenna.html"
PATCH_EXPECTED_RESONANCE_HZ = 2.45e9
PATCH_RESONANCE_TOLERANCE_HZ = 0.25e9


def patch_antenna_fixture() -> tuple[DesignIR, AnalysisSpec]:
    """Return the dimensions and excitation from the official openEMS tutorial."""
    design = DesignIR(
        design_id="openems-simple-patch-reference",
        name="openEMS simple patch antenna reference",
        layers=[{"name": "F.Cu"}, {"name": "B.Cu"}],
        nets=[{"id": "1", "name": "PATCH"}, {"id": "2", "name": "GND"}],
        zones=[
            {
                "id": "patch",
                "points": [[-16.0, -20.0], [16.0, -20.0], [16.0, 20.0], [-16.0, 20.0]],
                "layer": "F.Cu",
                "net_name": "PATCH",
            },
            {
                "id": "ground",
                "points": [[-30.0, -30.0], [30.0, -30.0], [30.0, 30.0], [-30.0, 30.0]],
                "layer": "B.Cu",
                "net_name": "GND",
            },
        ],
        stackup=[
            {"name": "F.Cu", "type": "copper", "thickness": 0.035},
            {
                "name": "substrate",
                "type": "core",
                "thickness": 1.524,
                "epsilon_r": 3.38,
                "loss_tangent": 0.001,
            },
            {"name": "B.Cu", "type": "copper", "thickness": 0.035},
        ],
    )
    spec = AnalysisSpec(
        analysis_id="openems-simple-patch-reference",
        mode="broadband_hf",
        net_names=["PATCH", "GND"],
        frequency_start_hz=1.0e9,
        frequency_stop_hz=3.0e9,
        frequency_points=101,
        options={
            "ports": [
                {
                    "start": [-6.0, 0.0, -1.524],
                    "stop": [-6.0, 0.0, 0.0],
                    "direction": "z",
                    "impedance_ohm": 50.0,
                    "excite": True,
                }
            ],
            "far_field": {
                "contract": FAR_FIELD_REQUEST_CONTRACT,
                "frequencies_hz": [PATCH_EXPECTED_RESONANCE_HZ],
                "theta": {"start_deg": 0.0, "stop_deg": 180.0, "points": 37},
                "phi": {"start_deg": -180.0, "stop_deg": 180.0, "points": 73},
                "radius_m": 1.0,
                "center_mm": [0.0, 0.0, 0.0],
            },
        },
    )
    return design, spec


def _evaluate_patch_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if result.get("status") != "completed":
        return {
            "status": "failed",
            "validation_status": "failed",
            "reason": result.get("message", "openEMS did not complete."),
        }
    frequencies = [float(value) for value in result.get("frequency_hz", [])]
    s11 = result.get("s_parameters", {}).get("s11", {})
    real = [float(value) for value in s11.get("real", [])]
    imag = [float(value) for value in s11.get("imag", [])]
    if not frequencies or len(frequencies) != len(real) or len(real) != len(imag):
        return {"status": "failed", "validation_status": "failed", "reason": "S11 output is incomplete."}
    magnitudes = [math.hypot(r, i) for r, i in zip(real, imag)]
    resonance_index = min(range(len(magnitudes)), key=magnitudes.__getitem__)
    resonance_hz = frequencies[resonance_index]
    resonance_error_hz = abs(resonance_hz - PATCH_EXPECTED_RESONANCE_HZ)
    far_field = result.get("far_field", {})
    radiated_power = [float(value) for value in far_field.get("radiated_power", {}).get("total_w", [])]
    directivity = [float(value) for value in far_field.get("directivity", {}).get("maximum_linear", [])]
    checks = {
        "resonance_in_reference_band": resonance_error_hz <= PATCH_RESONANCE_TOLERANCE_HZ,
        "s11_has_a_resonant_minimum": magnitudes[resonance_index] < 0.5,
        "positive_radiated_power": bool(radiated_power) and all(value > 0 for value in radiated_power),
        "positive_directivity": bool(directivity) and all(value > 0 for value in directivity),
    }
    passed = all(checks.values())
    return {
        "status": "passed" if passed else "failed",
        "validation_status": "reference_fixture_passed" if passed else "failed",
        "scope": "openems_adapter.simple_patch_antenna",
        "reference": REFERENCE_URL,
        "resonance_hz": resonance_hz,
        "expected_resonance_hz": PATCH_EXPECTED_RESONANCE_HZ,
        "resonance_error_hz": resonance_error_hz,
        "minimum_s11_linear": magnitudes[resonance_index],
        "maximum_directivity_linear": directivity,
        "radiated_power_w": radiated_power,
        "checks": checks,
        "limitations": [
            "This validates one reference geometry and the SPIKE-to-openEMS translation path only.",
            "It does not establish arbitrary PCB, cable, enclosure, immunity, or regulatory-compliance accuracy.",
        ],
    }


def run_patch_antenna_benchmark(
    output_directory: str | Path,
    *,
    mesh_resolution_mm: float = 5.0,
    max_timesteps: int = 30_000,
    timeout_seconds: int = 600,
) -> Dict[str, Any]:
    design, spec = patch_antenna_fixture()
    root = Path(output_directory).resolve()
    options = {
        "mesh_resolution_mm": float(mesh_resolution_mm),
        "air_padding_mm": 70.0,
        "dielectric_cells_per_layer": 4,
        "end_criteria": 1e-4,
        "max_timesteps": int(max_timesteps),
        "max_solver_time_s": int(timeout_seconds),
        "threads": 0,
    }
    prepared = prepare_openems_case(design, spec, root, options)
    if prepared.get("status") == "blocked":
        return {"status": "failed", "validation_status": "failed", "prepare": prepared, "case_dir": str(root)}
    result = run_openems_case(root, timeout_seconds=timeout_seconds)
    report = _evaluate_patch_result(result)
    report.update({
        "contract": "spike/openems-adapter-benchmark/v1",
        "mesh_resolution_mm": float(mesh_resolution_mm),
        "max_timesteps": int(max_timesteps),
        "case_dir": str(root),
        "solver_status": result.get("status"),
        "solver_model_status": result.get("model_status"),
        "duration_s": result.get("provenance", {}).get("duration_s", result.get("duration_s")),
    })
    return report


def evaluate_mesh_convergence(reports: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    values = [dict(report) for report in reports]
    if len(values) < 3 or any(report.get("status") != "passed" for report in values):
        return {
            "contract": "spike/openems-mesh-convergence/v1",
            "status": "failed",
            "validation_status": "not_validated",
            "reason": "Three passing reference runs are required.",
        }
    ordered = sorted(values, key=lambda value: float(value["mesh_resolution_mm"]), reverse=True)
    resonances = [float(value["resonance_hz"]) for value in ordered]
    directivities = [float(value["maximum_directivity_linear"][0]) for value in ordered]
    resonance_change = abs(resonances[-1] - resonances[-2]) / max(abs(resonances[-1]), 1.0)
    directivity_change = abs(directivities[-1] - directivities[-2]) / max(abs(directivities[-1]), 1e-30)
    passed = resonance_change <= 0.03 and directivity_change <= 0.10
    return {
        "contract": "spike/openems-mesh-convergence/v1",
        "status": "passed" if passed else "failed",
        "validation_status": "validated_for_reference_fixture" if passed else "not_validated",
        "scope": "openems_adapter.simple_patch_antenna",
        "mesh_resolution_mm": [float(value["mesh_resolution_mm"]) for value in ordered],
        "resonance_hz": resonances,
        "maximum_directivity_linear": directivities,
        "finest_pair_resonance_change": resonance_change,
        "finest_pair_directivity_change": directivity_change,
        "thresholds": {"resonance_relative": 0.03, "directivity_relative": 0.10},
        "reference": REFERENCE_URL,
    }
