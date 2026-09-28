# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Deterministic 10.3125 GBd qualification of the public linear SI workflow.

This is numerical regression evidence, not Ethernet protocol compliance.
"""

from __future__ import annotations

import json
from pathlib import Path
import platform
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from python.spike_core.si_workflow import REQUEST, run_si_workflow  # noqa: E402
from python.spike_core.sparameters import touchstone_text  # noqa: E402


BIT_RATE_HZ = 10_312_500_000.0
DELAY_S = 173e-12
VOLTAGE_GAIN = 0.8


def _grid(samples_per_ui: int, points: int = 513) -> np.ndarray:
    """Return a uniform DC grid whose inverse transform represents the rate exactly."""
    spacing_hz = BIT_RATE_HZ * samples_per_ui / (2 * points - 1)
    return np.arange(points, dtype=float) * spacing_hz


# The 513-point, 16-sample/UI construction defines the physical bandwidth used
# by the independent transform-period refinement below.
FIXED_BANDWIDTH_HZ = float(_grid(16)[-1])


def _known_channel(samples_per_ui: int, *, delay_s: float = DELAY_S) -> dict[str, Any]:
    frequencies = _grid(samples_per_ui)
    forward = VOLTAGE_GAIN * np.exp(-2j * np.pi * frequencies * delay_s)
    scattering = np.zeros((len(frequencies), 2, 2), dtype=complex)
    scattering[:, 1, 0] = forward
    scattering[:, 0, 1] = forward
    return {
        "kind": "touchstone",
        "name": "analytic-delayed-attenuator.s2p",
        "text": touchstone_text(frequencies, scattering),
    }


def _request(samples_per_ui: int, *, time_domain: bool = True) -> dict[str, Any]:
    return {
        "contract": REQUEST,
        "channel": _known_channel(samples_per_ui),
        "sources": [{"port": 0, "resistance_ohm": 50.0, "low_v": 0.0,
                     "high_v": 1.0, "rise_time_s": 20e-12, "fall_time_s": 20e-12}],
        "receivers": [{"port": 1, "resistance_ohm": 50.0, "capacitance_f": 0.0,
                       "vil_v": 0.2, "vih_v": 0.3}],
        "bit_rate_hz": BIT_RATE_HZ,
        "bit_count": 128,
        "run_time_domain": time_domain,
    }


def _transfer(result: dict[str, Any], port: int = 1) -> np.ndarray:
    trace = next(item["trace"] for item in result["loaded_transfers"]
                 if item["source_port"] == 0 and item["observed_port"] == port)
    return np.asarray([complex(point["real"], point["imag"]) for point in trace])


def _eye_height(result: dict[str, Any]) -> float | None:
    time_domain = result.get("time_domain", {})
    if time_domain.get("status") != "completed" or not time_domain.get("receivers"):
        return None
    return float(time_domain["receivers"][0]["eye_height_v"])


def _fixed_band_rc_request(points: int) -> dict[str, Any]:
    request = _request(16)
    # sqrt(L/C)=50 ohm, so this lossless line is matched; using the native RLGC
    # grid avoids text-rounding perturbations while N alone refines df/period.
    request["channel"] = {"kind": "rlgc", "coupled": False, "length_m": 0.01,
                          "resistance_ohm_per_m": 0.0, "inductance_h_per_m": 250e-9,
                          "capacitance_f_per_m": 100e-12, "loss_tangent": 0.0,
                          "frequency_points": points, "frequency_stop_hz": FIXED_BANDWIDTH_HZ,
                          "reference_impedance_ohm": 50.0}
    request["passives"] = [{"id": "convergence-c", "port": 1, "connection": "shunt",
                             "model": {"kind": "capacitor", "grade": "C0G",
                                       "capacitance_f": 1.2e-12, "esr_ohm": 0.0,
                                       "esl_h": 0.0, "leakage_ohm": 1e15}}]
    return request


def qualification_report() -> dict[str, Any]:
    fine = run_si_workflow(_request(16))
    coarse = run_si_workflow(_request(8))
    fine_frequencies = _grid(16)
    expected = 0.5 * VOLTAGE_GAIN * np.exp(-2j * np.pi * fine_frequencies * DELAY_S)
    transfer_error = float(np.max(np.abs(_transfer(fine) - expected)))

    # A shunt C behind a matched through path has H=1/(2+j*w*50*C).
    rc_request = _request(16, time_domain=False)
    rc_request["channel"] = {
        "kind": "touchstone", "name": "ideal-through.s2p",
        "text": touchstone_text(
            fine_frequencies,
            np.tile(np.array([[0, 1], [1, 0]], dtype=complex), (len(fine_frequencies), 1, 1)),
        ),
    }
    capacitance_f = 1.2e-12
    rc_request["passives"] = [{"id": "analytic-c", "port": 1, "connection": "shunt",
                                "model": {"kind": "capacitor", "grade": "C0G",
                                          "capacitance_f": capacitance_f, "esr_ohm": 0.0,
                                          "esl_h": 0.0, "leakage_ohm": 1e15}}]
    rc = run_si_workflow(rc_request)
    rc_expected = 1 / (2 + 2j * np.pi * fine_frequencies * 50 * capacitance_f)
    rc_error = float(np.max(np.abs(_transfer(rc) - rc_expected)))

    insufficient = _request(8)
    insufficient["channel"] = {
        "kind": "rlgc", "coupled": False, "length_m": 0.01,
        "resistance_ohm_per_m": 0.0, "inductance_h_per_m": 250e-9,
        "capacitance_f_per_m": 100e-12, "loss_tangent": 0.0,
        "frequency_points": 513, "frequency_stop_hz": float(_grid(2)[-1]),
        "reference_impedance_ohm": 50.0,
    }
    blocked = run_si_workflow(insufficient)
    exact_eye_request = _request(16)
    exact_eye_request["channel"] = _known_channel(16, delay_s=1 / BIT_RATE_HZ)
    exact_eye_request["sources"][0].update({"rise_time_s": 0.0, "fall_time_s": 0.0})
    exact_eye = run_si_workflow(exact_eye_request)
    exact_eye_height = _eye_height(exact_eye)
    fine_eye = _eye_height(fine)
    coarse_eye = _eye_height(coarse)
    sensitivity_delta = abs(fine_eye - coarse_eye) if fine_eye is not None and coarse_eye is not None else None

    refinement_points = [257, 513, 1025, 2049, 4097, 8193]
    refinement_results = [run_si_workflow(_fixed_band_rc_request(points)) for points in refinement_points]
    refinement_eyes = [_eye_height(result) for result in refinement_results]
    refinement_rates = [float(result["time_domain"]["represented_bit_rate_hz"])
                        if result.get("time_domain", {}).get("status") == "completed" else None
                        for result in refinement_results]
    refinement_rate_errors = [rate - BIT_RATE_HZ if rate is not None else None
                              for rate in refinement_rates]
    refinement_deltas = ([abs(refinement_eyes[i] - refinement_eyes[i - 1])
                          for i in range(1, len(refinement_eyes))]
                         if all(value is not None for value in refinement_eyes) else [])
    refinement_rate_exact = all(error is not None and abs(error) <= 0.01
                                for error in refinement_rate_errors)
    refinement_pass = (len(refinement_deltas) == len(refinement_points) - 1
                       and refinement_deltas[-1] <= 2e-4
                       and refinement_rate_exact)

    represented_rate = fine.get("time_domain", {}).get("represented_bit_rate_hz")
    exact_rate_error = abs(represented_rate - BIT_RATE_HZ) if represented_rate is not None else None

    criteria = [
        {"id": "exact_10g_rate_grid", "pass": bool(exact_rate_error is not None and exact_rate_error <= 0.01),
         "actual_hz": float(represented_rate) if represented_rate is not None else None, "expected_hz": BIT_RATE_HZ,
         "absolute_error_hz": float(exact_rate_error) if exact_rate_error is not None else None,
         "limit_hz": 0.01},
        {"id": "analytic_loaded_gain_phase", "pass": bool(transfer_error <= 2e-12),
         "max_complex_error": transfer_error, "limit": 2e-12},
        {"id": "analytic_rc_transfer", "pass": bool(rc_error <= 2e-12),
         "max_complex_error": rc_error, "limit": 2e-12},
        {"id": "matched_time_domain_eye", "pass": bool(exact_eye_height is not None and abs(exact_eye_height - 0.4) <= 1e-10),
         "actual_eye_height_v": exact_eye_height, "expected_eye_height_v": 0.4,
         "absolute_error_v": abs(exact_eye_height - 0.4) if exact_eye_height is not None else None, "limit_v": 1e-10,
         "delay_ui": 1.0, "samples_per_ui": 16},
        {"id": "bandwidth_sampling_sensitivity", "pass": bool(sensitivity_delta is not None and sensitivity_delta <= 0.01),
         "eye_height_8_spui_v": coarse_eye, "eye_height_16_spui_v": fine_eye,
         "absolute_delta_v": sensitivity_delta, "limit_v": 0.01},
        {"id": "fixed_band_frequency_grid_refinement_sensitivity", "pass": refinement_pass,
         "frequency_stop_hz": FIXED_BANDWIDTH_HZ, "frequency_points": refinement_points,
         "eye_height_v": refinement_eyes, "successive_delta_v": refinement_deltas,
         "represented_bit_rate_hz": refinement_rates,
         "represented_bit_rate_error_hz": refinement_rate_errors,
         "engineering_gate": {"monotonic_delta_contraction_required": False, "final_delta_limit_v": 2e-4,
                              "represented_rate_error_limit_hz": 0.01,
                              "normative": False, "is_error_bound": False},
         "interpretation": "Fixed bandwidth/source/load/RC and exact represented bit rate; refining N changes frequency spacing and transform period. Successive deltas are refinement evidence, not a strict monotonic convergence proof or solution-error estimate."},
        {"id": "insufficient_bandwidth_rejected", "pass": blocked["time_domain"]["status"] == "blocked",
         "status": blocked["time_domain"]["status"], "reason": blocked["time_domain"].get("reason")},
    ]
    return {
        "contract": "spike/serdes-reference-qualification/v1",
        "status": "pass" if all(item["pass"] for item in criteria) else "fail",
        "qualified_scope": "Linear NRZ numerical foundation at 10.3125 GBd for KR/SFI-like channel studies only.",
        "bit_rate_hz": BIT_RATE_HZ,
        "request_sha256": {
            "fine_16_spui": fine["request_sha256"],
            "coarse_8_spui": coarse["request_sha256"],
            "matched_eye": exact_eye["request_sha256"],
            "rc": rc["request_sha256"],
            "insufficient_bandwidth": blocked["request_sha256"],
            **{f"fixed_band_{points}": result["request_sha256"]
               for points, result in zip(refinement_points, refinement_results)},
        },
        "runtime": {
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "numpy_version": np.__version__,
        },
        "criteria": criteria,
        "production_qualified": False,
        "compliance_status": "not_evaluated",
        "limitations": [
            "No IEEE 802.3 electrical mask, COM, BER, jitter, CDR, equalization, training, or interoperability qualification.",
            "No 10GBASE-T PHY, PAM16 modulation, DSP, echo cancellation, FEC, or twisted-pair model.",
            "Analytic synthetic networks are numerical oracles, not measurements or measured-channel validation.",
            "The 8/16 samples-per-UI comparison changes sampled bandwidth and transform period; it is sensitivity evidence, not a controlled convergence proof.",
            "The fixed-band refinement uses the exact source clock and fractional receiver sampling; its 0.2 mV engineering gate is non-normative and is not an error bound.",
        ],
    }


def main() -> int:
    report = qualification_report()
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
