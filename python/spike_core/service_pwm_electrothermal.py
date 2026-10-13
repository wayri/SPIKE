# SPDX-License-Identifier: Apache-2.0
"""Strict owned-worker transport for the bounded PWM reference model."""
from .service_helpers import error_response, operation_id


def handle_pwm_electrothermal_request(method, params, *, request_id=None):
    if method not in {"validate_pwm_electrothermal", "run_pwm_electrothermal",
                      "validate_pwm_volume_electrothermal", "run_pwm_volume_electrothermal"}:
        return None
    try:
        if not isinstance(params, dict) or set(params) != {"request"}:
            raise ValueError("PWM_FIELDS: only request accepted")
        if "volume" in method:
            from .pwm_volume_electrothermal import validate_pwm_volume_electrothermal as validate, run_pwm_volume_electrothermal as run
        else:
            from .pwm_electrothermal import validate_pwm_electrothermal as validate, run_pwm_electrothermal as run
        if method.startswith("validate_"):
            result = validate(params["request"])
        else:
            from .worker_progress import emit_worker_progress
            token = operation_id(request_id)
            result = run(params["request"], progress=(lambda frame:
                emit_worker_progress(token, method, frame)) if token else None)
        return {"ok": True, "result": result}
    except (ValueError, TypeError, KeyError, ArithmeticError, RuntimeError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", "PWM electrothermal model is invalid or unavailable.",
            operation_id=operation_id(request_id), detail=str(exc),
            context={"method": method, "boundary": "pwm_electrothermal"}, error_type=type(exc).__name__)
