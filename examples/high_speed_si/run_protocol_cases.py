# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 SPIKE contributors.
"""Original synthetic NRZ protocol-rate studies through SPIKE's service API."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from python.spike_core.service import handle
from python.spike_core.sparameters import parse_touchstone_text

CASES = [
    ("ethernet_1g", "1000BASE-X host serial reference", 1e9, 1.25e9, 1, "8b/10b", 0.8),
    ("ethernet_10g", "10GBASE-R/KR NRZ reference", 10e9, 10.3125e9, 1, "64b/66b", 0.8),
    ("ethernet_100g", "100GBASE-KR4 representative lane", 100e9, 25.78125e9, 4,
     "64b/66b PCS, 256b/257b transcoding and RS-FEC architecture; not encoded here", 0.8),
    ("lvds_1g", "LVDS illustrative 1 GBd differential mode", None, 1e9, 1, "user-defined NRZ", 0.7),
    ("serdes_32g", "Generic 32 GBd NRZ SerDes", None, 32e9, 1, "user-defined NRZ", 0.8),
]


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def solve(request):
    response = handle({"method": "run_si_workflow", "params": {"request": request}})
    if not response.get("ok"):
        raise RuntimeError(response)
    return response["result"]


def request_for(rate, swing, points=513):
    # One scalar voltage/current is the differential mode, Zdiff = 100 ohm.
    # Thevenin +/-swing produces matched receive +/-swing/2.
    return {
        "contract": "spike/si-workflow-request/v1",
        "channel": {
            "kind": "rlgc", "coupled": False, "length_m": 0.08,
            "resistance_ohm_per_m": 8.0, "inductance_h_per_m": 500e-9,
            "capacitance_f_per_m": 50e-12, "loss_tangent": 0.006,
            "reference_impedance_ohm": 100.0, "frequency_points": points,
            "frequency_stop_hz": rate * 16 * 512 / 1025,
        },
        "sources": [{"port": 0, "resistance_ohm": 100.0,
                     "low_v": -swing, "high_v": swing,
                     "rise_time_s": 0.15 / rate, "fall_time_s": 0.15 / rate}],
        "receivers": [{"port": 1, "resistance_ohm": 100.0,
                       "capacitance_f": 0.15e-12, "vil_v": -0.1, "vih_v": 0.1}],
        "passives": [], "edits": [], "bit_rate_hz": rate, "bit_count": 256,
        "temperature_c": 25.0, "run_time_domain": True, "export_format": "RI",
    }


def transfer_trace(result):
    return next(item["trace"] for item in result["loaded_transfers"]
                if item["source_port"] == 0 and item["observed_port"] == 1)


def analytic_loaded(frequencies, request):
    """Scalar ABCD solution, independent of SPIKE's matrix-exponential wave solve."""
    line = request["channel"]
    f = np.asarray(frequencies)
    omega = 2 * np.pi * f
    series = line["resistance_ohm_per_m"] + 1j * omega * line["inductance_h_per_m"]
    shunt = omega * line["capacitance_f_per_m"] * (line["loss_tangent"] + 1j)
    gamma = np.sqrt(series * shunt)
    argument = gamma * line["length_m"]
    # sinh(gamma*l)/gamma -> l at DC, including finite series resistance.
    propagation = np.full(f.shape, line["length_m"], dtype=complex)
    nonzero = np.abs(gamma) > 0
    propagation[nonzero] = np.sinh(argument[nonzero]) / gamma[nonzero]
    a = np.cosh(argument)
    b = series * propagation
    c = shunt * propagation
    rs = request["sources"][0]["resistance_ohm"]
    rx = request["receivers"][0]
    yl = 1 / rx["resistance_ohm"] + 1j * omega * rx["capacitance_f"]
    return 1 / (a + b * yl + rs * (c + a * yl))


def eye(result):
    return result["time_domain"]["receivers"][0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    inputs = args.output / "protocol_inputs"
    results = args.output / "protocol_results"
    inputs.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)
    evidence = []
    for name, label, aggregate, rate, lanes, encoding, swing in CASES:
        request = request_for(rate, swing)
        result = solve(request)
        write_json(inputs / (name + ".json"), request)
        write_json(results / (name + ".json"), result)
        (results / (name + ".s2p")).write_text(result["touchstone"]["text"], encoding="ascii")
        trace = transfer_trace(result)
        frequencies = np.array([point["frequency_hz"] for point in trace])
        computed = np.array([complex(point["real"], point["imag"]) for point in trace])
        oracle = analytic_loaded(frequencies, request)
        error = float(np.max(np.abs(computed - oracle)))

        # Absolute time-domain oracle: lossless matched line exactly one UI long.
        exact = copy.deepcopy(request)
        exact["channel"].update(length_m=2e8 / rate, resistance_ohm_per_m=0,
                                loss_tangent=0)
        exact["sources"][0].update(rise_time_s=0, fall_time_s=0)
        exact["receivers"][0]["capacitance_f"] = 0
        exact_result = solve(exact)
        write_json(inputs / (name + "_matched_oracle.json"), exact)
        exact_eye = eye(exact_result)["eye_height_v"]

        # Hold physical bandwidth fixed; vary frequency spacing/transform period.
        refinements = []
        refinement_counts = (513, 1025, 2049, 4097, 8193) if name == "lvds_1g" else (513, 1025, 2049)
        for count in refinement_counts:
            refined = copy.deepcopy(request)
            refined["channel"]["frequency_points"] = count
            output = result if count == 513 else solve(refined)
            refined_trace = transfer_trace(output)
            expected = analytic_loaded([p["frequency_hz"] for p in refined_trace], refined)
            actual = np.array([complex(p["real"], p["imag"]) for p in refined_trace])
            refinements.append({
                "frequency_points": count, "request_sha256": output["request_sha256"],
                "eye_height_v": eye(output)["eye_height_v"],
                "represented_bit_rate_hz": output["time_domain"]["represented_bit_rate_hz"],
                "max_complex_transfer_error": float(np.max(np.abs(actual - expected))),
            })
        changes = [abs(refinements[k]["eye_height_v"] - refinements[k-1]["eye_height_v"])
                   for k in range(1, len(refinements))]
        insufficient = copy.deepcopy(request)
        insufficient["channel"]["frequency_stop_hz"] /= 8
        blocked = solve(insufficient)
        write_json(inputs / (name + "_insufficient_bandwidth.json"), insufficient)

        channel = parse_touchstone_text(result["touchstone"]["text"], name + ".s2p")
        s = channel.s_parameters()
        nearest = int(np.argmin(abs(channel.frequencies_hz - rate / 2)))
        metrics = {key: value for key, value in eye(result).items()
                   if key not in {"traces", "waveform"}}
        checks = {
            "completed": result["status"] == "completed",
            "analytic_loaded_transfer": error < 1e-10,
            "matched_eye_absolute": abs(exact_eye - swing) < 1e-10,
            "exact_rate": abs(result["time_domain"]["represented_bit_rate_hz"] - rate) < 0.01,
            "passive_channel": result["network"]["checks"]["passivity"]["status"] == "pass",
            "fixed_band_refinement": changes[-1] < 0.005,
            "refinement_absolute_transfer": all(p["max_complex_transfer_error"] < 1e-10 for p in refinements),
            "insufficient_bandwidth_blocked": blocked["time_domain"]["status"] == "blocked",
            "spatial_fields_withheld": result["field_maps"]["status"] == "unsupported",
            "qualification_withheld": not result["production_qualified"] and result["compliance_status"] == "not_evaluated",
        }
        record = {
            "id": name, "label": label, "aggregate_payload_rate_bps": aggregate,
            "architecture_lane_count": lanes, "simulated_lane_count": 1,
            "lane_symbol_rate_baud": rate, "modulation": "NRZ", "architecture_encoding": encoding,
            "stimulus": "PRBS7, no PCS encoding or FEC simulation",
            "ui_ps": 1e12 / rate, "nyquist_hz": rate / 2,
            "request_sha256": result["request_sha256"],
            "result_path": (results / (name + ".json")).relative_to(args.output).as_posix(),
            "input_path": (inputs / (name + ".json")).relative_to(args.output).as_posix(),
            "initial_2049_point_refinement_pass": changes[1] < 0.005,
            "samples_per_ui": result["time_domain"]["actual_samples_per_ui"],
            "frequency_stop_hz": request["channel"]["frequency_stop_hz"],
            "max_complex_loaded_transfer_error": error,
            "expected_matched_eye_v": swing, "actual_matched_eye_v": exact_eye,
            "matched_request_sha256": exact_result["request_sha256"],
            "loaded_eye": metrics,
            "channel_sample_near_nyquist_hz": float(channel.frequencies_hz[nearest]),
            "insertion_loss_near_nyquist_db": float(-20 * np.log10(abs(s[nearest, 1, 0]))),
            "return_loss_near_nyquist_db": float(-20 * np.log10(max(abs(s[nearest, 0, 0]), 1e-30))),
            "refinements": refinements, "successive_eye_change_v": changes,
            "insufficient_bandwidth_reason": blocked["time_domain"].get("reason"),
            "checks": checks, "status": "pass" if all(checks.values()) else "fail",
        }
        evidence.append(record)
        print(name, record["status"], "eye_v", metrics["eye_height_v"], "oracle_error", error, flush=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True).stdout.strip()
    report = {
        "contract": "spike/protocol-rate-study-evidence/v1",
        "status": "pass" if all(r["status"] == "pass" for r in evidence) else "fail",
        "backend": "python.spike_core.service.handle(run_si_workflow)",
        "backend_source_sha256": {name: hashlib.sha256((ROOT / "python" / "spike_core" / name).read_bytes()).hexdigest() for name in ("service.py", "si_workflow.py", "si_network_workflow.py", "si_channel.py", "si_symbol_clock.py", "sparameters.py")},
        "git_head": commit, "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "runtime": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "model_status": "experimental", "production_qualified": False, "compliance_status": "not_evaluated",
        "criteria": {"complex_transfer_absolute_tolerance": 1e-10,
                     "matched_eye_absolute_tolerance_v": 1e-10,
                     "fixed_band_final_eye_change_limit_v": 0.005,
                     "rate_error_limit_hz": 0.01, "normative": False,
                     "refinement_gate_is_error_bound": False},
        "cases": evidence,
    }
    write_json(results / "summary.json", report)
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

