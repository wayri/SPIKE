# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Source/frozen PAM3 behavioral probe; never loads a native model library."""
import math
import copy


def verify_si_material_runtime(executable, request):
    # Reuse original project test geometry, never an external implementation or
    # a board reduced/replaced to force numerical admission.
    from tests.python import test_si_material_scenario as fixtures
    design = fixtures.uniform_design()
    other = copy.deepcopy(design["zones"][0])
    other["id"] = "omitted-reference"
    other["outlines_mm"] = [[[100., 100.], [110., 100.], [110., 110.], [100., 110.]]]
    design["zones"].append(other)
    results = []
    for conductivity in (58e6, 29e6):
        prepared = request(executable, "prepare_si_material_scenario", {"design": design,
            "request": fixtures.scenario_request(design, conductivity)})["result"]
        if prepared["design"]["source"] != design["source"] or design["materials"][0]["conductivity_s_per_m"] is not None:
            raise RuntimeError("SI preparation mutated original design or lost source identity")
        result = request(executable, "run_si_uniform_channel", {"design": prepared["design"],
            "request": {**fixtures.channel_request(), "reference_zone_id": "zone-reference"}})["result"]
        extraction = result["extraction"]
        if extraction["geometry"]["omitted_reference_zone_ids"] != ["omitted-reference"] or result["production_qualified"] is not False:
            raise RuntimeError("Selected reference plane lost omissions or experimental status")
        expected = 1 / (conductivity * .00035 * .000035)
        if not math.isclose(extraction["rlgc_per_m"]["resistance_ohm_per_m"], expected, rel_tol=1e-12):
            raise RuntimeError("Prepared material resistance differs from independent Ohmic oracle")
        results.append(extraction)
    if results[0]["geometry_digest"] == results[1]["geometry_digest"]:
        raise RuntimeError("Material change reused a stale extraction identity")
    return {"status": "passed", "checks": ["immutable_preparation", "explicit_reference_zone", "ohmic_resistance", "material_identity"],
            "production_qualified": False, "scope": "Original synthetic inline packaging fixture, not a board qualification"}


def verify_si_execution_runtime(executable, request):
    value = {"contract": "spike/si-pam3-request/v1", "symbols": [0, 1, 2] * 32,
             "levels_v": [-0.4, 0.0, 0.4], "channel_impulse": [1.0],
             "symbol_rate_hz": 20e9, "samples_per_ui": 8}
    result = request(executable, "simulate_si_pam3", {"request": value})["result"]
    if (result.get("source", {}).get("modulation") != "PAM3" or
            result.get("production_qualified") is not False or result.get("compliance_status") != "not_evaluated"):
        raise RuntimeError("PAM3 runtime lost modulation identity or experimental status")
    if len(result["eyes"]) != 2 or result["errors"]["observed_symbol_errors"] != 0:
        raise RuntimeError("PAM3 runtime identity decisions differ from independent three-level oracle")
    for eye in result["eyes"]:
        if not math.isclose(eye["height_v"], .4, rel_tol=1e-12, abs_tol=1e-14):
            raise RuntimeError("PAM3 runtime identity eye opening is incorrect")
    rare = request(executable, "simulate_si_pam3", {"request": {
        **value, "levels_v": [-1., 0., 1.], "voltage_noise_rms_v": .05}})["result"]
    expected = (4 / 3) * .5 * math.erfc(.5 / (.05 * math.sqrt(2)))
    actual = rare["errors"]["expected_symbol_error_rate_gaussian"]
    if actual <= 0 or abs(actual / expected - 1) > 1e-12:
        raise RuntimeError("PAM3 runtime rare-error tail lost precision")
    return {"status": "passed", "checks": ["three_level_identity", "two_eye_openings", "rare_gaussian_tail"],
            "request_sha256": result["request_sha256"], "rare_expected_ser": actual,
            "production_qualified": False, "native_model_execution": "separate_trusted_development_api",
            "material_reference_workflow": verify_si_material_runtime(executable, request)}
