# SPDX-License-Identifier: Apache-2.0
"""Bounded worker routes for experimental EM/circuit/thermal composition."""

from __future__ import annotations

import json
from typing import Any

from .service_helpers import error_response


_METHODS = {
    "prepare_emerge_cosimulation_source",
    "solve_em_network_ac",
    "run_em_network_resistor_thermal",
    "run_em_network_resistor_cht",
    "run_em_spice_coupling",
    "run_em_body_heating",
    "run_pdn_dielectric_thermomechanical",
}
_PREPARE_FIELDS = {
    "result",
    "binding",
    "expected_case_sha256",
    "expected_script_sha256",
    "port_bindings",
    "wave_convention",
}
_REQUEST_LIMIT = 8 * 1024**2


def _bounded_request(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict) or set(params) != {"request"}:
        raise ValueError("EM_COSIM_FIELDS: exactly one request parameter is required")
    request = params["request"]
    try:
        encoded = json.dumps(
            request,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError(f"EM_COSIM_JSON: finite JSON request required: {exc}") from exc
    if len(encoded) > _REQUEST_LIMIT:
        raise ValueError("EM_COSIM_RESOURCE_LIMIT: request exceeds 8 MiB")
    value = json.loads(encoded)
    if not isinstance(value, dict):
        raise ValueError("EM_COSIM_REQUEST: request must be an object")
    return value


def handle_em_cosimulation_request(method: Any, params: Any) -> dict[str, Any] | None:
    """Run only the allowlisted owned implementations; never execute user code."""
    if method not in _METHODS:
        return None
    try:
        request = _bounded_request(params)
        if method == "prepare_emerge_cosimulation_source":
            if set(request) != _PREPARE_FIELDS:
                raise ValueError("EMERGE_COSIM_FIELDS: exact source-preparation fields required")
            from extensions.emerge_suite.cosimulation import prepare_cosimulation_source

            result = prepare_cosimulation_source(
                request["result"],
                request["binding"],
                expected_case_sha256=request["expected_case_sha256"],
                expected_script_sha256=request["expected_script_sha256"],
                port_bindings=request["port_bindings"],
                wave_convention=request["wave_convention"],
            )
        elif method == "solve_em_network_ac":
            from .em_network_ac import solve_em_network_ac

            result = solve_em_network_ac(request)
        elif method == "run_em_network_resistor_thermal":
            from .em_network_resistor_thermal import run_em_network_resistor_thermal

            result = run_em_network_resistor_thermal(request)
        elif method == "run_em_network_resistor_cht":
            from .em_network_resistor_cht import run_em_network_resistor_cht

            result = run_em_network_resistor_cht(request)
        elif method == "run_em_spice_coupling":
            from .em_spice_coupling import run_em_spice_coupling

            result = run_em_spice_coupling(request)
        elif method == "run_em_body_heating":
            from .em_body_heating import run_em_body_heating

            result = run_em_body_heating(request)
        else:
            from .pdn_dielectric_thermomechanical import run_pdn_dielectric_thermomechanical

            result = run_pdn_dielectric_thermomechanical(request)
        return {"ok": True, "result": result}
    except (ValueError, TypeError, KeyError, ArithmeticError, OverflowError, RecursionError,
            RuntimeError, OSError) as exc:
        kernel_code = str(getattr(exc, "code", "EM_COSIM_INVALID_REQUEST"))
        return error_response(
            "SPIKE-BE-IPC-E-0001",
            "EM co-simulation request is invalid, unsupported, or failed numerical admission.",
            detail=str(exc),
            context={"method": method, "kernel_code": kernel_code},
            error_type=type(exc).__name__,
        )
