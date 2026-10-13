# SPDX-License-Identifier: Apache-2.0
"""Offline co-simulation and recorded digital twin worker boundary."""
from .service_helpers import error_response


def handle_cosimulation_request(method, params):
    if method not in {"cosimulation_catalog", "run_cosimulation", "compare_digital_twin"}:
        return None
    try:
        from .cosimulation import bounded_digest, run_cosimulation
        bounded_digest(params)
        if method == "cosimulation_catalog":
            if params != {}:
                raise ValueError("Catalog takes no parameters")
            result = {"contract": "spike/cosimulation-catalog/v1", "model_status": "experimental",
                      "adapters": ["replay", "gain"], "coupling": "fixed_grid_explicit_lag",
                      "digital_twin": "recorded_exact_timestamp_comparison",
                      "unsupported": ["FMI", "live_device_IO", "HIL", "automatic_calibration"]}
        else:
            if not isinstance(params, dict) or set(params) != {"request"}:
                raise ValueError("Exactly one request parameter is required")
            if method == "run_cosimulation":
                result = run_cosimulation(params["request"])
            else:
                from .digital_twin import compare_digital_twin
                result = compare_digital_twin(params["request"])
        bounded_digest(result)
        return {"ok": True, "result": result}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", "Co-simulation request is invalid.",
                              detail=str(exc), context={"method": method}, error_type=type(exc).__name__)
