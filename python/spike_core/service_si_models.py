# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""SI inventory, material preparation and PAM3 routes; no model-library loader."""
from .service_helpers import error_response


def handle_si_model_request(method, params):
    if method == "prepare_si_material_scenario":
        from .service_si_materials import handle_si_material_request
        return handle_si_material_request(params)
    if method == "simulate_si_pam3":
        from .service_si_pam3 import handle_pam3_request
        return handle_pam3_request(params)
    if method not in {"inspect_si_ami_parameters", "inspect_si_ami_package"}:
        return None
    try:
        if not isinstance(params, dict):
            raise ValueError("SI model inventory parameters must be an object")
        from .si_ami_inventory import parse_ami_parameters, inspect_ami_package
        if method == "inspect_si_ami_parameters":
            if set(params) - {"text", "name"} or "text" not in params:
                raise ValueError("Exactly text and optional name are permitted")
            result = parse_ami_parameters(params["text"], params.get("name", "model.ami"))
        else:
            if set(params) != {"request"}:
                raise ValueError("Exactly one request is required")
            result = inspect_ami_package(params["request"])
        return {"ok": True, "result": result}
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", "SI model inventory failed admission.",
                              detail=str(exc), context={"method": method},
                              error_type=type(exc).__name__)
