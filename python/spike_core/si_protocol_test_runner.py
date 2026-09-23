"""Bounded SI protocol-suite execution over geometry-derived channel results.

The runner is orchestration, not a second solver.  It validates one declarative
suite, executes each admitted lane exactly once through ``si_channel``, and
projects the resulting RLGC/network/time-domain/eye evidence into explicit
per-analysis records.  It never evaluates licensed protocol limits or promotes
the experimental channel model to compliance evidence.
"""

from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from typing import Any, Callable, Mapping

from .design_ir_v2 import DesignIRV2
from .si_channel import REQUEST_CONTRACT as CHANNEL_REQUEST_CONTRACT
from .si_channel import SiChannelError, analyze_uniform_design_channel
from .si_protocol_suites import ANALYSES, canonical_si_protocol_suite, suite_digest


REQUEST_CONTRACT = "spike/si-protocol-test-suite-request/v1"
RESULT_CONTRACT = "spike/si-protocol-test-suite-result/v1"
MAXIMUM_LANES = 32
MAXIMUM_FREQUENCY_POINTS = 131_076
MAXIMUM_ESTIMATED_NUMERIC_BYTES = 134_217_728

_REQUEST_KEYS = {"contract", "suite", "lanes", "requested_tests", "resource_limits"}
_LANE_KEYS = {"lane_id", "channel_request"}
_RESOURCE_KEYS = {
    "maximum_lanes", "maximum_frequency_points", "maximum_estimated_numeric_bytes",
}


class SiProtocolTestRunnerError(ValueError):
    """Raised when suite execution is malformed or exceeds its hard bounds."""


def _canonical_digest(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _positive_limit(value: Any, name: str, hard_maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= hard_maximum:
        raise SiProtocolTestRunnerError(f"{name} must be an integer from 1 through {hard_maximum}.")
    return value


def _validate_request(request: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[str], dict[str, int]]:
    if not isinstance(request, Mapping):
        raise SiProtocolTestRunnerError("SI protocol test-suite request must be an object.")
    unknown = set(request) - _REQUEST_KEYS
    missing = {"contract", "suite", "lanes"} - set(request)
    if unknown or missing:
        raise SiProtocolTestRunnerError(
            f"SI protocol test-suite request keys are invalid; missing={sorted(missing)}, unknown={sorted(unknown)}."
        )
    if request.get("contract") != REQUEST_CONTRACT:
        raise SiProtocolTestRunnerError(f"contract must be {REQUEST_CONTRACT}.")
    suite = canonical_si_protocol_suite(request.get("suite"))

    raw_limits = request.get("resource_limits") or {}
    if not isinstance(raw_limits, Mapping) or set(raw_limits) - _RESOURCE_KEYS:
        raise SiProtocolTestRunnerError("resource_limits has unknown fields or is not an object.")
    limits = {
        "maximum_lanes": _positive_limit(raw_limits.get("maximum_lanes", MAXIMUM_LANES), "maximum_lanes", MAXIMUM_LANES),
        "maximum_frequency_points": _positive_limit(
            raw_limits.get("maximum_frequency_points", MAXIMUM_FREQUENCY_POINTS),
            "maximum_frequency_points", MAXIMUM_FREQUENCY_POINTS,
        ),
        "maximum_estimated_numeric_bytes": _positive_limit(
            raw_limits.get("maximum_estimated_numeric_bytes", MAXIMUM_ESTIMATED_NUMERIC_BYTES),
            "maximum_estimated_numeric_bytes", MAXIMUM_ESTIMATED_NUMERIC_BYTES,
        ),
    }

    raw_lanes = request.get("lanes")
    if not isinstance(raw_lanes, list) or not 1 <= len(raw_lanes) <= limits["maximum_lanes"]:
        raise SiProtocolTestRunnerError(f"lanes must contain 1..{limits['maximum_lanes']} entries.")
    lanes: list[dict[str, Any]] = []
    lane_ids: set[str] = set()
    total_frequencies = 0
    for index, raw_lane in enumerate(raw_lanes):
        if not isinstance(raw_lane, Mapping) or set(raw_lane) != _LANE_KEYS:
            raise SiProtocolTestRunnerError(f"lanes[{index}] must contain only lane_id and channel_request.")
        lane_id = raw_lane.get("lane_id")
        if not isinstance(lane_id, str) or not lane_id.strip() or len(lane_id) > 128 or lane_id in lane_ids:
            raise SiProtocolTestRunnerError(f"lanes[{index}].lane_id is empty, too long, or duplicated.")
        channel_request = raw_lane.get("channel_request")
        if not isinstance(channel_request, Mapping) or channel_request.get("contract") != CHANNEL_REQUEST_CONTRACT:
            raise SiProtocolTestRunnerError(
                f"lanes[{index}].channel_request must be a {CHANNEL_REQUEST_CONTRACT} object."
            )
        frequencies = channel_request.get("frequencies_hz")
        if not isinstance(frequencies, list):
            raise SiProtocolTestRunnerError(f"lanes[{index}].channel_request.frequencies_hz must be an array.")
        total_frequencies += len(frequencies)
        lane_ids.add(lane_id)
        lanes.append({"lane_id": lane_id, "channel_request": dict(channel_request)})
    if total_frequencies > limits["maximum_frequency_points"]:
        raise SiProtocolTestRunnerError(
            f"The requested {total_frequencies} frequency points exceed maximum_frequency_points={limits['maximum_frequency_points']}."
        )

    raw_tests = request.get("requested_tests")
    if raw_tests is None:
        tests = [str(item["id"]) for item in suite["analyses"]]
    else:
        if not isinstance(raw_tests, list) or not 1 <= len(raw_tests) <= len(ANALYSES):
            raise SiProtocolTestRunnerError("requested_tests must contain 1..15 analysis identifiers.")
        tests = []
        for index, value in enumerate(raw_tests):
            if not isinstance(value, str) or value not in ANALYSES or value in tests:
                raise SiProtocolTestRunnerError(f"requested_tests[{index}] is unsupported or duplicated.")
            tests.append(value)
    return suite, lanes, tests, limits


def preflight_si_suite_resources(request: Mapping[str, Any]) -> dict[str, int]:
    """Validate suite structure and count work without executing a channel solve."""
    _, lanes, _, _ = _validate_request(request)
    return {"lanes": len(lanes), "frequency_points": sum(
        len(lane["channel_request"]["frequencies_hz"]) for lane in lanes)}


def _trace_extrema(points: Any) -> dict[str, float] | None:
    if not isinstance(points, list) or not points:
        return None
    usable = [point for point in points if isinstance(point, Mapping) and isinstance(point.get("magnitude_db"), (int, float))]
    if not usable:
        return None
    minimum = min(usable, key=lambda point: float(point["magnitude_db"]))
    maximum = max(usable, key=lambda point: float(point["magnitude_db"]))
    return {
        "minimum_db": float(minimum["magnitude_db"]),
        "minimum_frequency_hz": float(minimum["frequency_hz"]),
        "maximum_db": float(maximum["magnitude_db"]),
        "maximum_frequency_hz": float(maximum["frequency_hz"]),
    }


def _completed(analysis_id: str, output_path: str, metrics: Mapping[str, Any] | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "analysis_id": analysis_id,
        "status": "completed",
        "reason": "Executed from the admitted geometry-derived channel result; no protocol limit was evaluated.",
        "output_path": output_path,
    }
    if metrics:
        record["metrics"] = dict(metrics)
    return record


def _blocked(analysis_id: str, reason: str) -> dict[str, Any]:
    return {"analysis_id": analysis_id, "status": "blocked", "reason": reason}


def _lane_test(analysis_id: str, result: Mapping[str, Any], channel_request: Mapping[str, Any]) -> dict[str, Any]:
    extraction = result.get("extraction") if isinstance(result.get("extraction"), Mapping) else {}
    network = result.get("network") if isinstance(result.get("network"), Mapping) else {}
    time_domain = result.get("time_domain") if isinstance(result.get("time_domain"), Mapping) else {}
    eye = result.get("eye") if isinstance(result.get("eye"), Mapping) else None
    differential = result.get("differential") if isinstance(result.get("differential"), Mapping) else None
    crosstalk = result.get("crosstalk") if isinstance(result.get("crosstalk"), Mapping) else None
    rlgc = extraction.get("rlgc_per_m") if isinstance(extraction.get("rlgc_per_m"), Mapping) else {}
    derived = extraction.get("derived") if isinstance(extraction.get("derived"), Mapping) else {}

    if analysis_id == "topology":
        geometry = extraction.get("geometry") if isinstance(extraction.get("geometry"), Mapping) else {}
        return _completed(analysis_id, "channel_result.extraction.geometry", {
            "length_m": geometry.get("length_m"), "path_mode": geometry.get("path_mode"),
            "signaling": channel_request.get("signaling", "single_ended"),
        })
    if analysis_id == "impedance":
        if "lossless_characteristic_impedance_ohm" in derived:
            return _completed(analysis_id, "channel_result.extraction.derived", {
                "lossless_characteristic_impedance_ohm": derived["lossless_characteristic_impedance_ohm"],
            })
        if network.get("input_impedance_port1"):
            return _completed(analysis_id, "channel_result.network.input_impedance_port1")
        return _blocked(analysis_id, "No scalar or swept input-impedance output was produced for this lane.")
    if analysis_id == "rlgc":
        return _completed(analysis_id, "channel_result.extraction.rlgc_per_m", {"matrix_valued": isinstance(rlgc.get("resistance_ohm_per_m"), list)})
    if analysis_id == "s_parameters":
        return _completed(analysis_id, "channel_result.network.traces", {"port_count": network.get("port_count"), "frequency_points": (network.get("frequency") or {}).get("count")})
    if analysis_id == "tdr_tdt":
        return _completed(analysis_id, "channel_result.time_domain", {"sample_count": (time_domain.get("processing") or {}).get("sample_count")})
    if analysis_id == "insertion_return_loss":
        traces = network.get("traces") if isinstance(network.get("traces"), Mapping) else {}
        return _completed(analysis_id, "channel_result.network.traces", {
            "return_loss_s11": _trace_extrema(traces.get("S11")),
            "insertion_loss_s21": _trace_extrema(traces.get("S21")),
        })
    if analysis_id == "next_fext":
        if crosstalk is None:
            return _blocked(analysis_id, "NEXT/FEXT requires an explicit coupled victim or differential partner in channel_request.victim_net.")
        return _completed(analysis_id, "channel_result.crosstalk", {
            "worst_next_db": (crosstalk.get("next") or {}).get("worst_transfer_db"),
            "worst_fext_db": (crosstalk.get("fext") or {}).get("worst_transfer_db"),
        })
    if analysis_id == "mode_conversion":
        if differential is None:
            return _blocked(analysis_id, "Mode-conversion output requires signaling=differential and an explicit partner net.")
        return _completed(analysis_id, "channel_result.network.mixed_mode", {"differential_reference_impedance_ohm": (differential.get("transform") or {}).get("differential_reference_impedance_ohm")})
    if analysis_id == "skew_delay":
        delays = network.get("group_delay_s21")
        if not isinstance(delays, list) or not delays:
            return _blocked(analysis_id, "No group-delay trace was produced for this lane.")
        finite = [float(item["group_delay_s"]) for item in delays if isinstance(item, Mapping) and isinstance(item.get("group_delay_s"), (int, float)) and isfinite(float(item["group_delay_s"]))]
        if not finite:
            return _blocked(analysis_id, "The group-delay trace has no finite samples.")
        return _completed(analysis_id, "channel_result.network.group_delay_s21", {"minimum_group_delay_s": min(finite), "maximum_group_delay_s": max(finite)})
    if analysis_id == "eye":
        if eye is None:
            return _blocked(analysis_id, "Eye execution requires explicit NRZ bit_rate_hz or PAM4 symbol_rate_hz/model inputs.")
        if isinstance(eye.get("pam4"), Mapping):
            pam4 = eye["pam4"]
            return _completed(analysis_id, "channel_result.eye.pam4", {
                "eye_heights_normalized": pam4.get("eye_heights_normalized"),
                "worst_ber_proxy": max(pam4.get("ber_proxies") or [0.5]),
            })
        return _completed(analysis_id, "channel_result.eye", {
            "eye_height_normalized": eye.get("eye_height_normalized"),
            "deterministic_isi_ber_estimate": eye.get("deterministic_isi_ber_estimate"),
        })
    if analysis_id == "jitter":
        if eye is None or not isinstance(eye.get("statistical"), Mapping):
            return _blocked(analysis_id, "Jitter execution requires an explicit channel_request.statistical_eye_model; no jitter distribution is inferred.")
        statistical = eye["statistical"]
        return _completed(analysis_id, "channel_result.eye.statistical", {
            "eye_width_at_target_ber_ui": statistical.get("eye_width_at_target_ber_ui"),
            "target_ber": statistical.get("target_ber"),
        })
    if analysis_id == "pam4":
        if eye is None or not isinstance(eye.get("pam4"), Mapping):
            return _blocked(analysis_id, "PAM4 execution requires explicit channel_request.symbol_rate_hz and pam4_model inputs; no Tx/Rx model is inferred.")
        pam4 = eye["pam4"]
        return _completed(analysis_id, "channel_result.eye.pam4", {
            "eye_heights_normalized": pam4.get("eye_heights_normalized"),
            "ber_proxies": pam4.get("ber_proxies"),
            "cdr_mode": (pam4.get("equalization") or {}).get("cdr_mode"),
        })
    if analysis_id == "power_aware":
        return _blocked(analysis_id, "No simultaneous-switching/power-aware source model is bound to this channel request.")
    if analysis_id == "compliance_review":
        return _blocked(analysis_id, "Licensed protocol limits, fixtures, masks, and independently validated models are not bound; compliance is not evaluated.")
    return _blocked(analysis_id, "This analysis is not executable by the bounded protocol test runner.")


def run_si_protocol_test_suite(
    design: DesignIRV2,
    request: Mapping[str, Any],
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Execute admitted lane analyses and preserve honest qualification."""

    suite, lanes, requested_tests, limits = _validate_request(request)
    lane_results: list[dict[str, Any]] = []
    total_frequency_points = 0
    total_numeric_bytes = 0
    completed_tests = 0
    blocked_tests = 0
    for lane in lanes:
        if cancel_check is not None and cancel_check():
            raise SiProtocolTestRunnerError("SI protocol test-suite execution was cancelled.")
        try:
            channel_result = analyze_uniform_design_channel(
                design, lane["channel_request"], cancel_check=cancel_check,
            )
        except SiChannelError as exc:
            raise SiProtocolTestRunnerError(f"Lane {lane['lane_id']!r} failed: {exc}") from exc
        resources = channel_result["resource_admission"]
        total_frequency_points += int(resources["frequency_points"])
        total_numeric_bytes += int(resources["estimated_numeric_bytes"])
        if total_frequency_points > limits["maximum_frequency_points"]:
            raise SiProtocolTestRunnerError("Actual frequency-point use exceeded the admitted suite limit.")
        if total_numeric_bytes > limits["maximum_estimated_numeric_bytes"]:
            raise SiProtocolTestRunnerError("Estimated numeric output exceeded the admitted suite byte limit.")
        tests = [_lane_test(analysis_id, channel_result, lane["channel_request"]) for analysis_id in requested_tests]
        completed_tests += sum(item["status"] == "completed" for item in tests)
        blocked_tests += sum(item["status"] == "blocked" for item in tests)
        lane_results.append({
            "lane_id": lane["lane_id"],
            "status": "completed",
            "channel_request_digest": _canonical_digest(lane["channel_request"]),
            "channel_result": channel_result,
            "tests": tests,
        })

    lane_delays: list[tuple[str, float]] = []
    for lane in lane_results:
        trace = lane["channel_result"]["network"].get("group_delay_s21") or []
        finite = [float(item["group_delay_s"]) for item in trace if isinstance(item, Mapping) and isinstance(item.get("group_delay_s"), (int, float)) and isfinite(float(item["group_delay_s"]))]
        if finite:
            lane_delays.append((lane["lane_id"], sum(finite) / len(finite)))
    skew = None
    if len(lane_delays) >= 2:
        earliest = min(lane_delays, key=lambda item: item[1])
        latest = max(lane_delays, key=lambda item: item[1])
        skew = {
            "contract": "spike/si-lane-delay-skew/v1",
            "status": "completed",
            "lane_average_group_delay_s": [{"lane_id": lane_id, "group_delay_s": delay} for lane_id, delay in lane_delays],
            "maximum_skew_s": latest[1] - earliest[1],
            "earliest_lane_id": earliest[0],
            "latest_lane_id": latest[0],
            "compliance_status": "not_evaluated",
        }

    return {
        "contract": RESULT_CONTRACT,
        "status": "completed",
        "model_status": "experimental",
        "production_qualified": False,
        "compliance_status": "not_evaluated",
        "suite": {
            "suite_id": suite["id"],
            "suite_sha256": suite_digest(suite),
            "family": suite["family"],
            "qualification": suite["qualification"],
        },
        "requested_tests": requested_tests,
        "lanes": lane_results,
        "bus_metrics": {"delay_skew": skew},
        "summary": {
            "lane_count": len(lane_results),
            "completed_tests": completed_tests,
            "blocked_tests": blocked_tests,
            "all_requested_tests_completed": blocked_tests == 0,
            "protocol_pass_claimed": False,
        },
        "resource_admission": {
            "actual_lanes": len(lane_results),
            "actual_frequency_points": total_frequency_points,
            "estimated_numeric_bytes": total_numeric_bytes,
            "hard_limits": limits,
            "cooperative_cancellation_supported": True,
        },
        "provenance": {
            "implementation": "SPIKE independent bounded SI protocol-test orchestration",
            "design_contract": design.contract,
            "design_id": design.design_id,
            "request_digest": _canonical_digest(dict(request)),
            "channel_result_contract": "spike/si-channel-result/v1",
        },
        "release_gate": {
            "state": "experimental_screening_only",
            "required_before_promotion": [
                "protocol-specific licensed fixtures and limits",
                "bound transmitter, receiver, package, connector, and via models",
                "independent solver and measured channel correlation",
                "protocol-specific compliance validation with uncertainty",
            ],
        },
    }


__all__ = [
    "MAXIMUM_ESTIMATED_NUMERIC_BYTES", "MAXIMUM_FREQUENCY_POINTS", "MAXIMUM_LANES",
    "REQUEST_CONTRACT", "RESULT_CONTRACT", "SiProtocolTestRunnerError",
    "run_si_protocol_test_suite",
]
