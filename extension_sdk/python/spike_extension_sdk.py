"""Small, dependency-free helpers for SPIKE process extensions.

Extensions remain separate trusted programs. This module only formats the
versioned JSON exchange; the SPIKE host validates returned analysis results.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping


def read_request(path: str | Path) -> dict[str, Any]:
    request = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(request, dict) or request.get("contract") != "spike/extension/v1":
        raise ValueError("Expected a spike/extension/v1 request.")
    context = request.get("context")
    if not isinstance(context, dict):
        raise ValueError("Extension request context must be an object.")
    return request


def mesh_exchange(request: Mapping[str, Any]) -> dict[str, Any]:
    """Return host-generated solver geometry and complete admitted mesh.

    ``mesh_preview`` is for display and may be sampled. Solvers must use the
    complete ``mesh`` topology or generate their own mesh from solver_geometry.
    """
    context = request.get("context")
    if not isinstance(context, Mapping):
        raise ValueError("Extension request context must be an object.")
    mesh = context.get("mesh")
    preview = context.get("mesh_preview")
    binding = context.get("mesh_binding")
    geometry = context.get("solver_geometry")
    if (not isinstance(mesh, dict) or mesh.get("contract") != "spike/hybrid-mesh-exchange/v1"
            or mesh.get("truncated") is not False or not isinstance(preview, dict)
            or not isinstance(binding, dict) or not isinstance(geometry, dict)):
        raise ValueError("The host did not supply a complete mesh exchange; declare mesh.read.")
    return {"mesh": mesh, "mesh_preview": preview, "mesh_binding": binding,
            "solver_geometry": geometry, "analysis_spec": context.get("analysis_spec")}


def analysis_result(
    request: Mapping[str, Any],
    *,
    analysis_id: str,
    mode: str,
    model_status: str,
    solver: str,
    summary: Mapping[str, Any],
    visualization: Mapping[str, Any] | None = None,
    fields: Mapping[str, Any] | None = None,
    networks: Mapping[str, Any] | None = None,
    probes: list[Mapping[str, Any]] | None = None,
    issues: list[Mapping[str, Any]] | None = None,
    provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an AnalysisResult bound to the exact board given by the host.

    The caller supplies the actual computed quantities, units, assumptions,
    and model status. No samples or qualification evidence are invented here.
    """
    context = request.get("context")
    binding = context.get("design_binding") if isinstance(context, Mapping) else None
    if not isinstance(binding, Mapping) or not binding.get("design_id") or not binding.get("digest_sha256"):
        raise ValueError("The host did not supply a DesignIR binding.")
    if not analysis_id or not mode or not model_status or not solver:
        raise ValueError("Analysis ID, mode, model status, and solver are required.")
    result_fields = dict(fields or {})
    if visualization is not None:
        result_fields["visualization"] = {**dict(visualization), "schema": "spike/result-visualization/v1"}
    result = {
        "contract": "spike/v1",
        "analysis_id": analysis_id,
        "status": "completed",
        "mode": mode,
        "model_status": model_status,
        "summary": dict(summary),
        "fields": result_fields,
        "networks": dict(networks or {}),
        "probes": [dict(item) for item in probes or []],
        "issues": [dict(item) for item in issues or []],
        "provenance": {**dict(provenance or {}), "design_id": binding["design_id"],
                       "design_digest_sha256": binding["digest_sha256"], "solver": solver,
                       **({"input_mesh_sha256": context["mesh_binding"]["mesh_digest_sha256"]}
                          if isinstance(context.get("mesh_binding"), Mapping) else {}),
                       **({"input_analysis_spec_sha256": context["mesh_binding"]["analysis_spec_digest_sha256"]}
                          if isinstance(context.get("mesh_binding"), Mapping) else {})},
    }
    json.dumps(result, allow_nan=False)
    return result


def analysis_envelope(result: Mapping[str, Any], *, title: str) -> dict[str, Any]:
    if not title or result.get("contract") != "spike/v1":
        raise ValueError("A title and spike/v1 AnalysisResult are required.")
    return {"contract": "spike/extension-result/v1", "status": "completed",
            "title": title, "data": {"analysis_result": dict(result)}}


def write_result(path: str | Path, envelope: Mapping[str, Any]) -> None:
    """Write strict JSON atomically inside the host-provided job directory."""
    target = Path(path)
    if envelope.get("contract") != "spike/extension-result/v1":
        raise ValueError("Expected a spike/extension-result/v1 envelope.")
    payload = json.dumps(dict(envelope), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, target)


__all__ = ["read_request", "mesh_exchange", "analysis_result", "analysis_envelope", "write_result"]
