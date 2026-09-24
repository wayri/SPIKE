"""Python access to the same versioned worker operations used by the desktop.

The caller supplies ordinary JSON values. Extension trust, solver admission,
and result validation remain in the worker; this module does not bypass them.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from typing import Any


class SpikeAutomationError(RuntimeError):
    """A worker operation failed or returned an invalid response."""


def _json_object(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping.")
    # A JSON round trip gives scripts the same finite, detached data boundary as
    # the desktop bridge and prevents later mutation of submitted requests.
    try:
        copied = json.loads(json.dumps(dict(value), allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain finite JSON-compatible values.") from exc
    if not isinstance(copied, dict):
        raise TypeError(f"{label} must be an object.")
    return copied


class SpikeAutomation:
    """Compose worker calls from Python without inventing a second solver API.

    ``dispatch`` defaults to the local worker's in-process handler. A test or
    remote transport may supply a function with the same request/response shape.
    ``call`` exposes every registered worker method; convenience methods cover
    the common extension exchange loop.
    """

    def __init__(self, dispatch: Callable[[dict[str, Any]], Mapping[str, Any]] | None = None) -> None:
        if dispatch is None:
            from .service import handle

            dispatch = handle
        self._dispatch = dispatch

    def call(self, method: str, params: Mapping[str, Any] | None = None) -> Any:
        if not isinstance(method, str) or not method.strip():
            raise ValueError("Worker method must be a non-empty string.")
        request = {"method": method, "params": _json_object(params or {}, "params")}
        response = self._dispatch(request)
        if not isinstance(response, Mapping) or not isinstance(response.get("ok"), bool):
            raise SpikeAutomationError(f"{method}: worker returned an invalid response.")
        if not response["ok"]:
            raise SpikeAutomationError(f"{method}: {response.get('error') or 'operation failed'}")
        return response.get("result")

    def extension_catalog(self) -> Mapping[str, Any]:
        return self.call("list_extensions")

    def invoke_extension(
        self,
        extension_id: str,
        contribution_id: str,
        *,
        design: Mapping[str, Any] | None = None,
        parameters: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        supplied = _json_object(context or {}, "context")
        if design is not None:
            supplied["design"] = _json_object(design, "design")
        supplied["parameters"] = _json_object(parameters or {}, "parameters")
        result = self.call("invoke_extension", {
            "extension_id": extension_id,
            "contribution_id": contribution_id,
            "context": supplied,
        })
        if not isinstance(result, Mapping):
            raise SpikeAutomationError("Extension returned no result envelope.")
        return result

    def run_steps(
        self,
        steps: Iterable[Mapping[str, Any]],
        *,
        on_result: Callable[[str, Any], None] | None = None,
    ) -> dict[str, Any]:
        """Run a named sequence; stop on the first failed or duplicate step."""
        output: dict[str, Any] = {}
        for index, raw in enumerate(steps):
            step = _json_object(raw, f"step {index + 1}")
            name = step.get("name", f"step-{index + 1}")
            if not isinstance(name, str) or not name or name in output:
                raise ValueError("Automation step names must be unique non-empty strings.")
            result = self.call(step.get("method", ""), step.get("params", {}))
            output[name] = result
            if on_result is not None:
                on_result(name, result)
        return output


__all__ = ["SpikeAutomation", "SpikeAutomationError"]
