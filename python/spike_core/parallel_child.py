# SPDX-License-Identifier: Apache-2.0
"""Single-request child for the bounded local parallel analysis pool.

This module deliberately does not import :mod:`service`.  Its fixed dispatch
table exposes only self-contained numerical operations; it cannot open a
client-supplied path, execute scripts, or discover extensions.
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any


MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_BYTES = 4 * 1024 * 1024

ALLOWED_METHODS = frozenset({
    "analyze_ac_power_integrity",
    "estimate_thermal",
    "evaluate_capacitor_placement",
    "extract_harness_round_wire_rlgc",
    "run_harness_mtl",
    "run_harness_pi",
    "run_harness_si",
    "run_internal_airflow",
    "run_smps_converter",
})


def _reject_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"Duplicate JSON object key: {key}")
        value[key] = item
    return value


def _decode_request(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise ValueError("Child request is empty or exceeds the 4 MiB limit.")
    value = json.loads(
        raw.decode("utf-8", errors="strict"),
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )
    if not isinstance(value, dict) or set(value) != {"id", "method", "params"}:
        raise ValueError("Child request must contain exactly id, method, and params.")
    if not isinstance(value["id"], str) or not value["id"]:
        raise ValueError("Child request id must be a nonempty string.")
    if value["method"] not in ALLOWED_METHODS:
        raise ValueError("Method is not allowed in the parallel child.")
    if not isinstance(value["params"], dict):
        raise ValueError("Child params must be an object.")
    return value


def _one_field(params: dict[str, Any], field: str) -> Any:
    if set(params) != {field} or not isinstance(params[field], dict):
        raise ValueError(f"This method requires exactly one object field: {field}.")
    return params[field]


def _dispatch(method: str, params: dict[str, Any]) -> Any:
    if method == "run_harness_pi":
        from .harness_pi import run_harness_pi
        return run_harness_pi(_one_field(params, "request"))
    if method == "run_harness_si":
        from .harness_signal import run_harness_si
        return run_harness_si(_one_field(params, "request"))
    if method == "run_harness_mtl":
        from .harness_mtl import run_harness_mtl
        return run_harness_mtl(_one_field(params, "request"))
    if method == "extract_harness_round_wire_rlgc":
        from .harness_rlgc_geometry import extract_parallel_round_rlgc
        return extract_parallel_round_rlgc(_one_field(params, "request"))
    if method == "run_internal_airflow":
        from .internal_airflow import run_internal_airflow
        return run_internal_airflow(_one_field(params, "request"))
    if method == "estimate_thermal":
        from .thermal import ThermalScenario, estimate_compact_thermal
        return estimate_compact_thermal(ThermalScenario(**_one_field(params, "scenario")))
    if method == "analyze_ac_power_integrity":
        from .ac_power_integrity import analyze_ac_power_integrity
        return analyze_ac_power_integrity(_one_field(params, "request"))
    if method == "evaluate_capacitor_placement":
        from .capacitor_placement import evaluate_capacitor_placement
        return evaluate_capacitor_placement(_one_field(params, "request"))
    if method == "run_smps_converter":
        from .smps_converter import evaluate_smps_converter
        return evaluate_smps_converter(_one_field(params, "request"))
    raise ValueError("Method is not allowed in the parallel child.")


def _response_bytes(response: dict[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            response, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        encoded = json.dumps({
            "id": response.get("id"),
            "ok": False,
            "error": {
                "code": "PARALLEL_CHILD_RESULT_INVALID",
                "type": type(exc).__name__,
                "message": "Analysis returned a value that is not finite JSON.",
            },
            "meta": response.get("meta", {}),
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) <= MAX_OUTPUT_BYTES:
        return encoded
    return json.dumps({
        "id": response.get("id"),
        "ok": False,
        "error": {
            "code": "PARALLEL_CHILD_OUTPUT_LIMIT",
            "type": "OutputLimitError",
            "message": "Analysis response exceeds the 4 MiB child output limit.",
        },
        "meta": response.get("meta", {}),
    }, sort_keys=True, separators=(",", ":")).encode("utf-8")


def main() -> int:
    started = time.perf_counter()
    request_id: Any = None
    method = "unknown"
    try:
        request = _decode_request(sys.stdin.buffer.read(MAX_INPUT_BYTES + 1))
        request_id = request["id"]
        method = request["method"]
        result = _dispatch(method, request["params"])
        response: dict[str, Any] = {"id": request_id, "ok": True, "result": result}
    except Exception as exc:
        response = {
            "id": request_id,
            "ok": False,
            "error": {
                "code": "PARALLEL_CHILD_REJECTED",
                "type": type(exc).__name__,
                "message": str(exc)[:4096],
            },
        }
    response["meta"] = {
        "contract": "spike/parallel-child-meta/v1",
        "method": method,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
    }
    sys.stdout.buffer.write(_response_bytes(response) + b"\n")
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ALLOWED_METHODS", "main"]
