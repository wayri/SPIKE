"""Convert native circuit output into SPIKE's shared analysis result contract.

The native MNA engine has no implicit knowledge of PCB coordinates.  This
adapter therefore publishes circuit waveforms and network values, but never
fabricates renderer-facing spatial fields.  A later field/circuit coupling
stage may add spatial data only after applying an explicit geometry binding.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List

from .contracts import AnalysisResult, ValidationIssue


def _issue(item: Dict[str, Any]) -> ValidationIssue:
    return ValidationIssue(
        code=str(item.get("code", "NATIVE_CIRCUIT_ERROR")),
        severity=str(item.get("severity", "error")),
        message=str(item.get("message", "Native circuit execution failed.")),
        path=str(item.get("path", "")),
        suggestion=str(item.get("suggestion", "")),
        status=str(item.get("status", "open")),
    )


def _maximum_absolute(values: Iterable[float]) -> float:
    return max((abs(float(value)) for value in values), default=0.0)


def _series_magnitude(value: Any) -> List[float]:
    if isinstance(value, dict):
        return [float(item) for item in value.get("magnitude", [])]
    if isinstance(value, list):
        return [float(item) for item in value]
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return [float(value)]
    return []


def _waveforms(mode: str, data: Dict[str, Any]) -> Dict[str, Any]:
    waveforms: Dict[str, Any] = {}
    if mode == "transient":
        waveforms["time"] = list(data.get("time_s", []))
    elif mode == "ac":
        waveforms["frequency"] = list(data.get("frequency_hz", []))
    for node, values in (data.get("node_voltage_v") or {}).items():
        waveforms[f"v({node})"] = _series_magnitude(values)
    for identifier, values in (data.get("element_current_a") or {}).items():
        waveforms[f"i({identifier})"] = _series_magnitude(values)
    power_key = "element_complex_power_va" if mode == "ac" else "element_power_w"
    for identifier, values in (data.get(power_key) or {}).items():
        waveforms[f"p({identifier})"] = _series_magnitude(values)
    return waveforms


def native_mna_to_analysis_result(
    native_result: Dict[str, Any],
    request: Dict[str, Any],
) -> AnalysisResult:
    """Return a traceable ``AnalysisResult`` for a native MNA execution."""

    native_status = str(native_result.get("status", "failed"))
    native_mode = str(native_result.get("mode") or (request.get("analysis") or {}).get("mode", "operating_point"))
    mode = {"operating_point": "dc", "ac": "ac", "transient": "transient"}.get(native_mode, native_mode)
    issues = [_issue(item) for item in native_result.get("issues", []) if isinstance(item, dict)]
    validation = native_result.get("validation") or {}
    if native_status == "blocked":
        issues.extend(_issue(item) for item in validation.get("issues", []) if isinstance(item, dict))

    data = native_result.get("data") if isinstance(native_result.get("data"), dict) else {}
    diagnostics = native_result.get("diagnostics") if isinstance(native_result.get("diagnostics"), dict) else {}
    waveforms = _waveforms(native_mode, data)
    node_series = data.get("node_voltage_v") or {}
    current_series = data.get("element_current_a") or {}
    power_key = "element_complex_power_va" if native_mode == "ac" else "element_power_w"
    power_series = data.get(power_key) or {}

    max_voltage = max((_maximum_absolute(_series_magnitude(value)) for value in node_series.values()), default=0.0)
    max_current = max((_maximum_absolute(_series_magnitude(value)) for value in current_series.values()), default=0.0)
    max_power = max((_maximum_absolute(_series_magnitude(value)) for value in power_series.values()), default=0.0)

    fields: Dict[str, Any] = {}
    if waveforms:
        fields["waveforms"] = waveforms
    if native_mode == "ac":
        fields["complex_waveforms"] = {
            "node_voltage_v": node_series,
            "branch_current_a": data.get("branch_current_a", {}),
            "element_current_a": current_series,
            "element_complex_power_va": power_series,
        }

    result = AnalysisResult(
        analysis_id=str(request.get("request_id", "native-mna")),
        status=native_status,
        mode=mode,
        model_status=str(native_result.get("model_status", "experimental")),
        summary={
            "analysis_kind": native_mode,
            "point_count": int(diagnostics.get("points", 0) or 0),
            "node_count": len(node_series),
            "element_count": len(request.get("elements", [])),
            "maximum_absolute_node_voltage_v": max_voltage,
            "maximum_absolute_element_current_a": max_current,
            "maximum_absolute_element_power_w_or_va": max_power,
            "condition_number_max": diagnostics.get("condition_number_max"),
            "relative_residual_max": diagnostics.get("relative_residual_max"),
        },
        fields=fields,
        networks={
            "circuit": {
                "ground_node": str(request.get("ground_node", "0")),
                "nodes": sorted(str(node) for node in node_series),
                "elements": [
                    {
                        "id": str(element.get("id", "")),
                        "type": str(element.get("type", "")),
                        "positive_node": str(element.get("positive_node", "")),
                        "negative_node": str(element.get("negative_node", "")),
                        "source_assignment_id": str(element.get("source_assignment_id", "")),
                        "source_component_ref": str(element.get("source_component_ref", "")),
                    }
                    for element in request.get("elements", [])
                    if isinstance(element, dict)
                ],
                "operating_point": data if native_mode == "operating_point" else {},
            }
        },
        issues=issues,
        provenance={
            **(native_result.get("provenance") or {}),
            "native_result_contract": native_result.get("contract"),
            "native_request_contract": request.get("contract"),
            "spatial_binding": "not_supplied",
            "spatial_visualization": "not_generated",
        },
    )
    return result


__all__ = ["native_mna_to_analysis_result"]
