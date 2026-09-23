"""Translation and execution against SPIKE's existing native linear MNA engine."""

from __future__ import annotations

import copy
import math
from dataclasses import replace
from typing import Any, Mapping

try:
    from python.spike_core.native_mna import (
        REQUEST_CONTRACT as NATIVE_REQUEST_CONTRACT,
        run_native_mna,
        validate_native_mna_request,
    )
except ModuleNotFoundError as exc:
    if exc.name != "python":
        raise
    # Installed/PYTHONPATH layouts expose both packages at top level.
    from spike_core.native_mna import (  # type: ignore[no-redef]
        REQUEST_CONTRACT as NATIVE_REQUEST_CONTRACT,
        run_native_mna,
        validate_native_mna_request,
    )

from .contracts import CircuitProject, CircuitResult, MeasureDirective, ProbeDescriptor


COMPILED_CONTRACT = "spikes/compiled-netlist/v1"


def _hierarchy_metadata(project: CircuitProject, *, include_instances: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "instance_count": len(project.hierarchy),
        "flattened_element_count": len(project.elements),
        "path_separator": ":",
    }
    if include_instances:
        result["instances"] = [instance.to_dict() for instance in project.hierarchy]
    return result


def _native_element(element: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": element.name,
        "type": element.kind,
        "positive_node": element.positive_node,
        "negative_node": element.negative_node,
    }
    value_fields = {
        "resistor": "resistance_ohm",
        "capacitor": "capacitance_f",
        "inductor": "inductance_h",
    }
    if element.kind in value_fields:
        result[value_fields[element.kind]] = element.value
    elif element.kind in {"vcvs", "vccs"}:
        result["control_positive_node"] = element.control_positive_node
        result["control_negative_node"] = element.control_negative_node
        result["gain" if element.kind == "vcvs" else "transconductance_s"] = element.value
    elif element.kind in {"cccs", "ccvs"}:
        result["control_source_id"] = element.control_source_id
        result["gain" if element.kind == "cccs" else "transresistance_ohm"] = element.value
    else:
        result["dc_value"] = element.value
    return result


def native_request(project: CircuitProject) -> dict[str, Any]:
    """Create the operating-point request used directly or per DC sweep point."""

    analysis: dict[str, Any] = {"mode": "operating_point"}
    if project.analysis.mode == "transient":
        analysis = {
            "mode": "transient",
            "time_step_s": project.analysis.time_step_s,
            "stop_time_s": project.analysis.stop_time_s,
        }
    return {
        "contract": NATIVE_REQUEST_CONTRACT,
        "request_id": f"spikes-{project.source_sha256[:16] or 'memory'}",
        "ground_node": "0",
        "analysis": analysis,
        "elements": [_native_element(element) for element in project.elements],
        "resource_limits": {"memory_limit_gb": 2.0, "linear_backend": "auto"},
    }


def compile_project(project: CircuitProject) -> dict[str, Any]:
    """Return a JSON-compatible compiled adapter record and validation."""

    request = native_request(project)
    return {
        "contract": COMPILED_CONTRACT,
        "status": "ready" if (validation := validate_native_mna_request(request))["valid"] else "blocked",
        "project": project.to_dict(),
        "native_request_template": request,
        "sweep": project.analysis.to_dict() if project.analysis.mode == "dc_sweep" else None,
        "ac": project.analysis.to_dict() if project.analysis.mode == "ac" else None,
        "transient": project.analysis.to_dict() if project.analysis.mode == "transient" else None,
        "hierarchy": _hierarchy_metadata(project, include_instances=True),
        "step_variants": len(project.step_variants),
        "measurements": [measure.to_dict() for measure in project.measurements],
        "validation": validation,
        "limitations": [
            "This parser accepts bounded R, C, L, V, I, diode, E/G/F/H, and affine single-control B syntax plus positional X/.subckt hierarchy; this reference adapter remains linear-only and rejects its diode elements.",
            "Bounded arithmetic parameters, subcircuit overrides, global nodes, and root-confined include/library expansion elaborate before adapter validation.",
            "Scoped model cards and primitives outside the declared subset are rejected.",
            "Operating-point, single-source DC, single-excitation linear AC, and strict fixed-step .tran TSTEP TSTOP analyses are accepted.",
            "Linear parameter STEP and scalar MEASURE directives are orchestrated by ordinary run; native-run rejects them rather than ignoring them.",
            "Transient integration uses the existing Python native-MNA reference adapter and fixed-step backward Euler; it is not the owned C++ transient solver.",
            "Results inherit the experimental validation status of spike.native.linear_mna.",
        ],
    }


def _sweep_values(start: float, stop: float, step: float) -> list[float]:
    count = int(math.floor(abs((stop - start) / step) + 1e-12)) + 1
    values = [start + index * step for index in range(count)]
    tolerance = max(abs(start), abs(stop), 1.0) * 1e-12
    if values and abs(values[-1] - stop) <= tolerance:
        values[-1] = stop
    return values


def _probe_value(probe: ProbeDescriptor, data: Mapping[str, Any]) -> float:
    if probe.quantity == "node_voltage":
        values = data.get("node_voltage_v", {})

        def voltage(node: str) -> float:
            return 0.0 if node == "0" else float(values[node])

        result = voltage(probe.targets[0])
        if len(probe.targets) == 2:
            result -= voltage(probe.targets[1])
        return result
    key = "element_current_a" if probe.quantity == "element_current" else "element_power_w"
    return float(data[key][probe.targets[0]])


def _probe_payload(probes: tuple[ProbeDescriptor, ...], data: Mapping[str, Any]) -> dict[str, Any]:
    return {
        probe.name: {"descriptor": probe.to_dict(), "value": _probe_value(probe, data)}
        for probe in probes
    }


def _series_probe_payload(
    probes: tuple[ProbeDescriptor, ...], data: Mapping[str, Any], point_count: int
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for probe in probes:
        values: list[float] = []
        for index in range(point_count):
            point_data = {
                "node_voltage_v": {
                    name: series[index] for name, series in data["node_voltage_v"].items()
                },
                "element_current_a": {
                    name: series[index] for name, series in data["element_current_a"].items()
                },
                "element_power_w": {
                    name: series[index] for name, series in data["element_power_w"].items()
                },
            }
            values.append(_probe_value(probe, point_data))
        result[probe.name] = {"descriptor": probe.to_dict(), "values": values}
    return result


def _measure_probe_values(probe: ProbeDescriptor, data: Mapping[str, Any]) -> float | list[float]:
    if "time_s" in data:
        count = len(data["time_s"])
    elif "sweep" in data:
        count = len(data["sweep"]["values"])
    else:
        return _probe_value(probe, data)
    return [
        _probe_value(probe, {
            "node_voltage_v": {name: values[index] for name, values in data["node_voltage_v"].items()},
            "element_current_a": {name: values[index] for name, values in data["element_current_a"].items()},
            "element_power_w": {name: values[index] for name, values in data["element_power_w"].items()},
        })
        for index in range(count)
    ]


def _one_measurement(measure: MeasureDirective, data: Mapping[str, Any]) -> dict[str, Any]:
    values = _measure_probe_values(measure.probe, data)
    base: dict[str, Any] = {
        "status": "completed", "operation": measure.operation,
        "probe": measure.probe.to_dict(), "unit": measure.probe.unit,
    }
    if isinstance(values, float):
        return base | {"value": values}
    axis = list(data["time_s"] if measure.analysis == "tran" else data["sweep"]["values"])
    if measure.operation == "find":
        assert measure.at_value is not None
        at = measure.at_value
        if axis[0] > axis[-1]:
            axis.reverse()
            values.reverse()
        tolerance = max(abs(axis[0]), abs(axis[-1]), abs(at), 1.0) * 1.0e-12
        if at < axis[0] - tolerance or at > axis[-1] + tolerance:
            raise ValueError(f"AT={at:g} is outside the simulated axis.")
        if at <= axis[0] + tolerance:
            value = values[0]
        elif at >= axis[-1] - tolerance:
            value = values[-1]
        else:
            upper = next(index for index, coordinate in enumerate(axis) if coordinate >= at)
            if abs(axis[upper] - at) <= tolerance:
                value = values[upper]
            else:
                lower = upper - 1
                fraction = (at - axis[lower]) / (axis[upper] - axis[lower])
                value = values[lower] + fraction * (values[upper] - values[lower])
        return base | {"value": value, "at": at, "interpolation": "linear"}

    selected = list(range(len(axis)))
    if measure.from_value is not None:
        assert measure.to_value is not None
        selected = [
            index for index, coordinate in enumerate(axis)
            if measure.from_value <= coordinate <= measure.to_value
        ]
        base["window"] = {"from": measure.from_value, "to": measure.to_value}
    if not selected:
        raise ValueError("Measurement window contains no simulated samples.")
    samples = [values[index] for index in selected]
    if measure.operation == "max":
        value = max(samples)
    elif measure.operation == "min":
        value = min(samples)
    elif measure.operation == "avg":
        value = sum(samples) / len(samples)
    else:
        value = math.sqrt(sum(sample * sample for sample in samples) / len(samples))
    return base | {"value": value, "sample_count": len(samples)}


def _measurements(project: CircuitProject, data: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for measure in project.measurements:
        try:
            result[measure.name] = _one_measurement(measure, data)
        except (KeyError, ValueError, ArithmeticError) as exc:
            result[measure.name] = {
                "status": "failed", "operation": measure.operation,
                "probe": measure.probe.to_dict(),
                "issue": {"code": "SPIKES_MEASURE_FAILED", "message": str(exc)},
            }
    return result


def _failed_result(project: CircuitProject, native: Mapping[str, Any], *, point: float | None = None) -> CircuitResult:
    raw_issues = list(native.get("issues", ()))
    validation = native.get("validation", {})
    if not raw_issues and isinstance(validation, Mapping):
        raw_issues.extend(validation.get("issues", ()))
    issues = []
    for raw_issue in raw_issues:
        issue = dict(raw_issue)
        if point is not None:
            issue["sweep_value"] = point
        issues.append(issue)
    if not issues:
        issues.append({
            "code": "SPIKES_NATIVE_RUN_BLOCKED",
            "severity": "error",
            "message": "The native MNA request did not complete.",
            "path": "native_mna",
            **({"sweep_value": point} if point is not None else {}),
        })
    return CircuitResult(
        status=str(native.get("status", "failed")),
        model_status=str(native.get("model_status", "unsupported")),
        analysis=project.analysis.to_dict(),
        issues=tuple(issues),
        diagnostics=dict(native.get("diagnostics", {})),
        provenance={
            "adapter": "python.spikes.runner",
            "source_sha256": project.source_sha256,
            "hierarchy": _hierarchy_metadata(project),
            "native": dict(native.get("provenance", {})),
        },
    )


def run_project(project: CircuitProject) -> CircuitResult:
    """Run an operating point, DC sweep, or bounded linear transient."""

    if project.steps:
        point_results: list[dict[str, Any]] = []
        probe_series: dict[str, Any] = {
            probe.name: {"descriptor": probe.to_dict(), "by_step": []}
            for probe in project.probes
        }
        measurement_series: dict[str, Any] = {
            measure.name: {"directive": measure.to_dict(), "by_step": []}
            for measure in project.measurements
        }
        for variant in project.step_variants:
            point_project = replace(
                project, elements=variant.elements, steps=(), step_variants=()
            )
            point_result = run_project(point_project)
            parameters = {name: value for name, value in variant.parameters}
            if point_result.status != "completed":
                return CircuitResult(
                    status="failed", model_status=point_result.model_status,
                    analysis=project.analysis.to_dict(),
                    diagnostics={"completed_step_variants": len(point_results)},
                    issues=tuple(point_result.issues) + ({
                        "code": "SPIKES_STEP_POINT_FAILED", "severity": "error",
                        "message": "A nested STEP variant did not complete.",
                        "parameters": parameters,
                    },),
                    provenance=dict(point_result.provenance) | {"step_parameters": parameters},
                )
            point_results.append({
                "parameters": parameters, "data": dict(point_result.data),
                "diagnostics": dict(point_result.diagnostics),
                "measurements": dict(point_result.measurements),
            })
            for name in probe_series:
                probe_series[name]["by_step"].append({
                    "parameters": parameters, "result": point_result.probes[name]
                })
            for name in measurement_series:
                measurement_series[name]["by_step"].append({
                    "parameters": parameters,
                    "result": point_result.measurements[name],
                })
        return CircuitResult(
            status="completed", model_status="experimental",
            analysis=project.analysis.to_dict(),
            data={
                "step_axes": [step.to_dict() for step in project.steps],
                "points": point_results,
            },
            probes=probe_series,
            measurements=measurement_series,
            diagnostics={
                "step_variants": len(point_results),
                "nesting_order": [step.parameter for step in project.steps],
                "ordering": "leftmost_axis_outermost",
            },
            provenance={
                "adapter": "python.spikes.runner",
                "source_sha256": project.source_sha256,
                "step_orchestration": "deterministic_cartesian",
            },
        )

    request = native_request(project)
    if project.analysis.mode == "operating_point":
        native = run_native_mna(request)
        if native.get("status") != "completed":
            return _failed_result(project, native)
        data = dict(native["data"])
        return CircuitResult(
            status="completed",
            model_status=str(native.get("model_status", "experimental")),
            analysis=project.analysis.to_dict(),
            data=data,
            probes=_probe_payload(project.probes, data),
            measurements=_measurements(project, data),
            diagnostics=dict(native.get("diagnostics", {})),
            issues=tuple(native.get("issues", ())),
            provenance={
                "adapter": "python.spikes.runner",
                "source_sha256": project.source_sha256,
                "hierarchy": _hierarchy_metadata(project),
                "native": dict(native.get("provenance", {})),
            },
        )

    if project.analysis.mode == "ac":
        from .analyses import AcExcitation, AcSweep, run_ac_analysis

        analysis = project.analysis
        assert analysis.frequency_points is not None
        assert analysis.start_frequency_hz is not None
        assert analysis.stop_frequency_hz is not None
        source = next(
            element for element in project.elements
            if element.name == analysis.source
        )
        ac = run_ac_analysis(
            project,
            AcSweep(
                start_hz=analysis.start_frequency_hz,
                stop_hz=analysis.stop_frequency_hz,
                points=analysis.frequency_points,
                scale="linear" if analysis.frequency_scale == "lin" else "log",
            ),
            AcExcitation(
                source=analysis.source,
                magnitude=source.ac_magnitude,
                phase_deg=source.ac_phase_deg,
            ),
        )
        return CircuitResult(
            status=str(ac.get("status", "failed")),
            model_status=str(ac.get("model_status", "unsupported")),
            analysis=project.analysis.to_dict(),
            data=dict(ac.get("data", {})),
            probes=dict(ac.get("probes", {})),
            diagnostics=dict(ac.get("diagnostics", {})),
            issues=tuple(ac.get("issues", ())),
            provenance={
                **dict(ac.get("provenance", {})),
                "deck_directive": ".ac",
                "source_sha256": project.source_sha256,
                "hierarchy": _hierarchy_metadata(project),
            },
        )

    if project.analysis.mode == "transient":
        native = run_native_mna(request)
        if native.get("status") != "completed":
            return _failed_result(project, native)
        data = dict(native["data"])
        times = data.get("time_s", ())
        return CircuitResult(
            status="completed",
            model_status=str(native.get("model_status", "experimental")),
            analysis=project.analysis.to_dict(),
            data=data,
            probes=_series_probe_payload(project.probes, data, len(times)),
            measurements=_measurements(project, data),
            diagnostics=dict(native.get("diagnostics", {})),
            issues=tuple(native.get("issues", ())),
            provenance={
                "adapter": "python.spikes.runner",
                "source_sha256": project.source_sha256,
                "hierarchy": _hierarchy_metadata(project),
                "transient_engine": {
                    "implementation": "python.spike_core.native_mna",
                    "integration": "fixed_step_backward_euler",
                    "owned_cpp_transient": False,
                },
                "native": dict(native.get("provenance", {})),
            },
        )

    sweep = project.analysis
    assert sweep.start is not None and sweep.stop is not None and sweep.step is not None
    axis = _sweep_values(sweep.start, sweep.stop, sweep.step)
    source_index = next(
        index for index, element in enumerate(request["elements"])
        if element["id"].upper() == sweep.source.upper()
    )
    node_series: dict[str, list[float]] = {}
    current_series: dict[str, list[float]] = {}
    power_series: dict[str, list[float]] = {}
    residuals: list[float] = []
    conditions: list[float] = []
    backend: dict[str, Any] = {}

    for point in axis:
        point_request = copy.deepcopy(request)
        point_request["request_id"] = f"{request['request_id']}-{len(residuals)}"
        point_request["elements"][source_index]["dc_value"] = point
        native = run_native_mna(point_request)
        if native.get("status") != "completed":
            return _failed_result(project, native, point=point)
        point_data = native["data"]
        for name, value in point_data["node_voltage_v"].items():
            node_series.setdefault(name, []).append(float(value))
        for name, value in point_data["element_current_a"].items():
            current_series.setdefault(name, []).append(float(value))
        for name, value in point_data["element_power_w"].items():
            power_series.setdefault(name, []).append(float(value))
        diagnostics = native.get("diagnostics", {})
        residuals.append(float(diagnostics.get("relative_residual_max", 0.0)))
        condition = diagnostics.get("condition_number_max")
        if condition is not None:
            conditions.append(float(condition))
        backend = dict(diagnostics.get("linear_backend", {}))

    data = {
        "sweep": {
            "source": sweep.source,
            "unit": "V" if sweep.source.rsplit(":", 1)[-1].startswith("V") else "A",
            "values": axis,
        },
        "node_voltage_v": node_series,
        "element_current_a": current_series,
        "element_power_w": power_series,
    }
    probe_values = _series_probe_payload(project.probes, data, len(axis))

    return CircuitResult(
        status="completed",
        model_status="experimental",
        analysis=project.analysis.to_dict(),
        data=data,
        probes=probe_values,
        measurements=_measurements(project, data),
        diagnostics={
            "points": len(axis),
            "relative_residual_max": max(residuals, default=0.0),
            "condition_number_max": max(conditions) if conditions else None,
            "linear_backend": backend,
        },
        provenance={
            "adapter": "python.spikes.runner",
            "source_sha256": project.source_sha256,
            "hierarchy": _hierarchy_metadata(project),
            "native": {
                "solver": "spike.native.linear_mna",
                "formulation": "modified_nodal_analysis",
                "sweep_orchestration": "independent_operating_points",
            },
        },
    )


__all__ = ["COMPILED_CONTRACT", "compile_project", "native_request", "run_project"]
