# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Yawar B (wayri) and SPIKE contributors
"""Bounded inline preparation; large retained designs use the local API."""
import json
from .service_helpers import error_response

MAX_INLINE_BYTES = 8 * 1024 * 1024


def handle_si_material_request(params):
    try:
        if not isinstance(params, dict) or set(params) != {"design", "request"}:
            raise ValueError("Exactly design and request are required")
        encoded = json.dumps(params, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_INLINE_BYTES:
            raise ValueError("Inline preparation exceeds 8 MiB; use the retained in-process API without truncating the design")
        from .si_material_scenario import prepare_si_material_scenario
        result = prepare_si_material_scenario(params["design"], params["request"])
        if len(json.dumps(result, separators=(",", ":"), allow_nan=False).encode("utf-8")) > MAX_INLINE_BYTES:
            raise ValueError("Prepared inline result exceeds 8 MiB; use the retained in-process API")
        return {"ok": True, "result": result}
    except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", "SI material scenario failed admission.",
                              detail=str(exc), context={"method": "prepare_si_material_scenario"},
                              error_type=type(exc).__name__)
