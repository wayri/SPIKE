# SPDX-License-Identifier: Apache-2.0
"""Narrow IPC admission for inert IBIS compilation and explicit native execution."""
from .service_helpers import error_response

METHODS = {"compile_ibis_behavioral", "run_ibis_behavioral", "inspect_ibis_behavioral_runtime"}


def handle_ibis_behavioral_request(method, params):
    if method not in METHODS:
        return None
    try:
        if not isinstance(params, dict):
            raise ValueError("IBIS parameters must be an object")
        if method == "inspect_ibis_behavioral_runtime":
            if set(params) - {"executable"} or ("executable" in params and not isinstance(params["executable"], str)):
                raise ValueError("Runtime inspection permits only an optional executable path")
            from .solvers.signal_integrity.receivers.ibis_behavioral_execution import inspect_ibis_behavioral_runtime
            result = inspect_ibis_behavioral_runtime(**params)
        elif method == "compile_ibis_behavioral":
            if set(params) != {"request"}:
                raise ValueError("Compilation requires exactly one structured request")
            from .solvers.signal_integrity.receivers.ibis_behavioral import compile_ibis_behavioral
            result = compile_ibis_behavioral(params["request"])
        else:
            if set(params) != {"request", "executable", "executable_sha256", "execution_requested"}:
                raise ValueError("Execution requires request, reviewed runtime identity and explicit intent")
            if params["execution_requested"] is not True:
                raise ValueError("Native execution must be explicitly requested")
            from .solvers.signal_integrity.receivers.ibis_behavioral_execution import run_ibis_behavioral
            result = run_ibis_behavioral(**params)
        return {"ok": True, "result": result}
    except (ValueError, TypeError, KeyError, ArithmeticError, OSError, RecursionError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", "IBIS behavioral request failed admission or execution.",
                              detail=str(exc), context={"method": method}, error_type=type(exc).__name__)
