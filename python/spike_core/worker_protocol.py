"""JSON-lines process loop shared by source and frozen workers."""

from __future__ import annotations

import json
import sys
import time
from typing import Any, Callable

from .errors import SpikeError, envelope_from_exception
from .service_helpers import error_response, operation_id


def serve_json_lines(
    handler: Callable[[dict[str, Any]], dict[str, Any]], worker_version: str,
) -> int:
    for line in sys.stdin:
        started = time.perf_counter()
        request_id = None
        method = "unknown"
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise TypeError("Worker requests must be JSON objects")
            request_id = request.get("id")
            method = str(request.get("method", "unknown"))
            response = {"id": request_id, **handler(request)}
            if response.get("ok") is False and "error_detail" not in response:
                legacy_code = str(response.get("error_code", ""))
                normalized = error_response(
                    "SPIKE-BE-IPC-E-0001",
                    str(response.get("error") or "The worker rejected the request."),
                    operation_id=operation_id(request_id),
                    context={"method": method, "legacy_error_code": legacy_code},
                    error_type=str(response.get("type") or "WorkerRequestError"),
                )
                response.update(normalized)
                if legacy_code:
                    response["legacy_error_code"] = legacy_code
        except Exception as exc:  # never corrupt the worker protocol stream
            expected = (json.JSONDecodeError, TypeError, ValueError, SpikeError)
            code = "SPIKE-BE-IPC-E-0001" if isinstance(exc, expected) else "SPIKE-BE-APP-C-9999"
            envelope = envelope_from_exception(
                exc, fallback_code=code, operation_id=operation_id(request_id),
            )
            response = {
                "id": request_id,
                "ok": False,
                "error": envelope["message"],
                "type": type(exc).__name__,
                "error_code": envelope["code"],
                "error_detail": envelope,
            }
        response["meta"] = {
            "contract": "spike/worker-response-meta/v1",
            "method": method,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "worker_version": worker_version,
        }
        sys.stdout.write(json.dumps(response, default=str) + "\n")
        sys.stdout.flush()
    return 0


__all__ = ["serve_json_lines"]
