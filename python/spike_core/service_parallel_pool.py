# SPDX-License-Identifier: Apache-2.0
"""Desktop pool boundary; enrollment/private keys never enter project data."""
from .service_helpers import error_response, operation_id


def handle_parallel_request(method, params, *, request_id=None):
    try:
        if not isinstance(params, dict) or set(params) != ({"request"} if method == "run_parallel_batch" else set()):
            raise ValueError("Unexpected parallel-pool fields.")
        from .parallel_pool import pool_catalog, run_parallel_batch
        result = pool_catalog() if method == "parallel_pool_catalog" else run_parallel_batch(params["request"])
        return {"ok": True, "result": result}
    except (ValueError, TypeError, KeyError, RuntimeError, OSError) as exc:
        return error_response("SPIKE-BE-IPC-E-0001", "Parallel pool rejected the request.",
            operation_id=operation_id(request_id), detail=str(exc), context={"method": method},
            error_type=type(exc).__name__)
