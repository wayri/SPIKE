# SPDX-License-Identifier: MIT
"""Child-side API for user-authored Python scripts in the desktop workspace."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import traceback
from pathlib import Path
from typing import Any

from .automation import SpikeAutomation


MAX_OUTPUT = 1_000_000


class _CappedText(io.TextIOBase):
    def __init__(self) -> None:
        self.parts: list[str] = []
        self.length = 0
        self.truncated = False

    def write(self, value: str) -> int:
        value = str(value)
        available = MAX_OUTPUT - self.length
        if available > 0:
            kept = value[:available]
            self.parts.append(kept)
            self.length += len(kept)
        if len(value) > available:
            self.truncated = True
        return len(value)

    def getvalue(self) -> str:
        return "".join(self.parts) + ("\n[output truncated]" if self.truncated else "")


class SpikeScriptAPI:
    """Small script facade; worker calls still pass through normal admission."""

    def __init__(self, context: dict[str, Any]) -> None:
        self.design = context.get("design")
        self.results = context.get("results")
        self._binding = context.get("design_binding")
        self._trusted_extension_ids = context.get("trusted_extension_ids", [])
        self._automation: SpikeAutomation | None = None
        self._published: dict[str, Any] | None = None

    def _worker(self) -> SpikeAutomation:
        if self._automation is None:
            self._automation = SpikeAutomation()
            from . import service
            for extension_id in self._trusted_extension_ids:
                service._extension_registry.trust(extension_id)
        return self._automation

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if method == "run_python_script":
            raise ValueError("Nested Python workspace runs are not supported.")
        return self._worker().call(method, params)

    def extensions(self) -> Any:
        return self._worker().extension_catalog()

    def invoke_extension(self, extension_id: str, contribution_id: str,
                         parameters: dict[str, Any] | None = None) -> Any:
        """Run a trusted adapter with the current board and declared context."""
        catalog = self.extensions()
        entry = next((item for item in catalog.get("extensions", []) if item.get("id") == extension_id), None)
        if entry is None:
            raise ValueError(f"Extension is not installed: {extension_id}")
        permissions = entry.get("permissions", [])
        context: dict[str, Any] = {}
        if "results.read" in permissions and self.results is not None:
            context["results"] = self.results
        reply = self._worker().invoke_extension(
            extension_id, contribution_id,
            design=self.design if "design.read" in permissions else None,
            parameters=parameters, context=context)
        analysis = reply.get("data", {}).get("analysis_result") if isinstance(reply.get("data"), dict) else None
        if isinstance(analysis, dict):
            provenance = analysis.get("provenance")
            if isinstance(provenance, dict):
                analysis = {**analysis, "provenance": {
                    **provenance, "script_upstream_extension_id": extension_id}}
            self.publish_result(analysis)
        return reply

    def publish_result(self, result: dict[str, Any]) -> None:
        """Offer a design-bound AnalysisResult to the viewer after host admission."""
        if self._binding is None:
            raise ValueError("Load a board before publishing an analysis result.")
        if not isinstance(result, dict):
            raise TypeError("Published result must be an AnalysisResult object.")
        try:
            json.dumps(result, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Published result contains a non-finite or non-JSON value.") from exc
        self._published = result

    def publish_scalar_field(self, name: str, samples: list[dict[str, Any]], *,
                             mode: str = "dc", solver: str = "python-script",
                             model_status: str = "unvalidated", summary: dict[str, Any] | None = None) -> None:
        """Publish one explicitly named board field without implying other physics."""
        if self._binding is None:
            raise ValueError("Load a board before publishing a field.")
        if not isinstance(name, str) or not name or not isinstance(samples, list):
            raise ValueError("Field name and sample array are required.")
        import uuid
        self.publish_result({
            "contract": "spike/v1", "analysis_id": f"python-{uuid.uuid4()}",
            "status": "completed", "mode": mode, "model_status": model_status,
            "summary": summary or {}, "fields": {"visualization": {
                "schema": "spike/result-visualization/v1", "scalar_fields": {name: samples}}},
            "networks": {}, "probes": [], "issues": [],
            "provenance": {"design_id": self._binding["design_id"],
                           "design_digest_sha256": self._binding["digest_sha256"],
                           "solver": solver},
        })

    @property
    def published_result(self) -> dict[str, Any] | None:
        return self._published


def run(request: dict[str, Any]) -> dict[str, Any]:
    output = _CappedText()
    errors = _CappedText()
    api = SpikeScriptAPI(request.get("context", {}))
    code = request["code"]
    status = "completed"
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        try:
            compiled = compile(code, "<SPIKE Python workspace>", "exec")
            exec(compiled, {"__name__": "__main__", "spike": api})
        except BaseException:
            status = "failed"
            traceback.print_exc(limit=12)
    return {"contract": "spike/python-script-result/v1", "status": status,
            "stdout": output.getvalue(), "stderr": errors.getvalue(),
            "return_code": 0 if status == "completed" else 1,
            "published_result": api.published_result if status == "completed" else None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    result = run(request)
    Path(args.result).write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
