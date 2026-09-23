"""Execution of parsed SPIKES projects against the owned C++ C ABI."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from .contracts import AnalysisDirective, CircuitProject, CircuitResult, ProbeDescriptor
from .native_abi import NativeCircuit, load_native_library


def _populate(circuit: NativeCircuit, project: CircuitProject) -> None:
    for element in project.elements:
        common = (element.name, element.positive_node, element.negative_node)
        if element.kind == "resistor":
            circuit.add_resistor(*common, element.value)
        elif element.kind == "capacitor":
            circuit.add_capacitor(
                *common, element.value,
                initial_voltage_v=element.initial_condition,
            )
        elif element.kind == "inductor":
            circuit.add_inductor(
                *common, element.value,
                initial_current_a=element.initial_condition,
            )
        elif element.kind == "diode":
            assert element.diode_model is not None
            # The native DC ABI consumes the electrical junction terms.  The
            # flicker-noise terms remain in the project model for the biased
            # frequency-domain noise analysis.
            circuit.add_diode(
                *common,
                saturation_current_a=element.diode_model.saturation_current_a,
                emission_coefficient=element.diode_model.emission_coefficient,
                temperature_k=element.diode_model.temperature_k,
            )
        elif element.kind in {"voltage_source", "current_source"}:
            prefix = "voltage" if element.kind == "voltage_source" else "current"
            if element.waveform is None:
                getattr(circuit, f"add_{prefix}_source")(*common, element.value)
            elif element.waveform.kind == "pulse":
                initial, pulsed, delay, rise, fall, width, period = element.waveform.pulse
                getattr(circuit, f"add_pulse_{prefix}_source")(
                    *common, initial_value=initial, pulsed_value=pulsed,
                    delay_s=delay, rise_time_s=rise, fall_time_s=fall,
                    pulse_width_s=width, period_s=period,
                )
            else:
                getattr(circuit, f"add_pwl_{prefix}_source")(
                    *common, element.waveform.points
                )
        elif element.kind == "voltage_controlled_switch":
            assert element.control_positive_node is not None
            assert element.control_negative_node is not None
            assert element.switch_model is not None
            circuit.add_voltage_controlled_switch(
                *common, element.control_positive_node,
                element.control_negative_node, **element.switch_model.to_dict(),
            )
        else:
            raise ValueError(f"Owned native runner does not support {element.kind}.")


def _nodes(project: CircuitProject) -> tuple[str, ...]:
    values = {"0"}
    for element in project.elements:
        values.update((element.positive_node, element.negative_node))
        if element.control_positive_node is not None:
            values.add(element.control_positive_node)
        if element.control_negative_node is not None:
            values.add(element.control_negative_node)
    return tuple(sorted(values, key=lambda item: (item != "0", item)))


def _probe_value(
    probe: ProbeDescriptor, data: dict[str, Any], index: int | None = None
) -> float:
    def select(table: dict[str, Any], name: str) -> float:
        value = table[name]
        return float(value if index is None else value[index])

    if probe.quantity == "node_voltage":
        value = select(data["node_voltage_v"], probe.targets[0])
        if len(probe.targets) == 2:
            value -= select(data["node_voltage_v"], probe.targets[1])
        return value
    table = (
        "element_current_a"
        if probe.quantity == "element_current"
        else "element_power_w"
    )
    return select(data[table], probe.targets[0])


def _probes(
    project: CircuitProject, data: dict[str, Any], point_count: int | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for probe in project.probes:
        payload: dict[str, Any] = {"descriptor": probe.to_dict()}
        if point_count is None:
            payload["value"] = _probe_value(probe, data)
        else:
            payload["values"] = [
                _probe_value(probe, data, index) for index in range(point_count)
            ]
        result[probe.name] = payload
    return result


def _failure(
    project: CircuitProject,
    status: str,
    message: str,
    diagnostics: dict[str, Any],
    library: Path,
) -> CircuitResult:
    return CircuitResult(
        status="failed",
        model_status="experimental",
        analysis=project.analysis.to_dict(),
        diagnostics=diagnostics,
        issues=({
            "code": "SPIKES_NATIVE_SOLVE_FAILED",
            "severity": "error",
            "message": message or status,
            "path": "owned_cpp_kernel",
        },),
        provenance={
            "solver": "SPIKES owned C++ kernel",
            "library": str(library),
            "native_status": status,
            "source_sha256": project.source_sha256,
        },
    )


def run_native_project(
    project: CircuitProject,
    library_path: str | Path,
    *,
    integration_method: str = "hybrid_trapezoidal",
) -> CircuitResult:
    """Run one operating-point or transient project through the owned kernel."""

    if project.steps or project.measurements:
        raise ValueError(
            ".step and .measure currently execute only through the bounded Python reference runner."
        )

    if project.analysis.mode == "dc_sweep":
        sweep = project.analysis
        assert sweep.start is not None and sweep.stop is not None and sweep.step is not None
        count = int(math.floor(abs((sweep.stop - sweep.start) / sweep.step) + 1e-12)) + 1
        axis = [sweep.start + index * sweep.step for index in range(count)]
        if axis and abs(axis[-1] - sweep.stop) <= 1e-12 * max(1.0, abs(sweep.stop)):
            axis[-1] = sweep.stop
        source_index = next(
            (
                index for index, element in enumerate(project.elements)
                if element.name.upper() == sweep.source.upper()
            ),
            None,
        )
        if source_index is None:
            raise ValueError(f"DC sweep source {sweep.source} is not present in the circuit.")
        source = project.elements[source_index]
        if source.kind not in {"voltage_source", "current_source"}:
            raise ValueError("DC sweep target must be an independent voltage or current source.")
        node_series: dict[str, list[float]] = {}
        current_series: dict[str, list[float]] = {}
        power_series: dict[str, list[float]] = {}
        residuals: list[float] = []
        for point in axis:
            elements = list(project.elements)
            elements[source_index] = replace(source, value=point, waveform=None)
            point_project = replace(
                project,
                elements=tuple(elements),
                analysis=AnalysisDirective(mode="operating_point"),
            )
            point_result = run_native_project(
                point_project, library_path, integration_method=integration_method
            )
            if point_result.status != "completed":
                return CircuitResult(
                    status=point_result.status,
                    model_status=point_result.model_status,
                    analysis=project.analysis.to_dict(),
                    diagnostics=dict(point_result.diagnostics) | {"failed_sweep_value": point},
                    issues=point_result.issues,
                    provenance=dict(point_result.provenance) | {"sweep_value": point},
                )
            point_data = point_result.data
            for name, value in point_data["node_voltage_v"].items():
                node_series.setdefault(name, []).append(float(value))
            for name, value in point_data["element_current_a"].items():
                current_series.setdefault(name, []).append(float(value))
            for name, value in point_data["element_power_w"].items():
                power_series.setdefault(name, []).append(float(value))
            residuals.append(float(point_result.diagnostics.get("residual_inf_norm", 0.0)))
        data = {
            "sweep": {
                "source": sweep.source,
                "unit": "V" if source.kind == "voltage_source" else "A",
                "values": axis,
            },
            "node_voltage_v": node_series,
            "element_current_a": current_series,
            "element_power_w": power_series,
        }
        return CircuitResult(
            status="completed",
            model_status="experimental",
            analysis=project.analysis.to_dict(),
            data=data,
            probes=_probes(project, data, len(axis)),
            diagnostics={
                "points": len(axis),
                "residual_inf_norm_max": max(residuals, default=0.0),
            },
            provenance={
                "solver": "SPIKES owned C++ kernel",
                "implementation": "independent_native_operating_points",
                "library": str(Path(library_path).resolve()),
                "source_sha256": project.source_sha256,
            },
        )
    library = load_native_library(library_path)
    node_names = _nodes(project)
    element_names = tuple(element.name for element in project.elements)
    with library.circuit() as circuit:
        _populate(circuit, project)
        if project.analysis.mode == "operating_point":
            with circuit.solve_operating_point() as result:
                diagnostics = result.diagnostics()
                if result.status != "converged":
                    return _failure(
                        project, result.status, result.message, diagnostics, library.path
                    )
                data = {
                    "node_voltage_v": {
                        name: result.node_voltage(name) for name in node_names
                    },
                    "element_current_a": {
                        name: result.element_current(name) for name in element_names
                    },
                    "element_power_w": {
                        name: result.element_power(name) for name in element_names
                    },
                }
                return CircuitResult(
                    status="completed",
                    model_status="experimental",
                    analysis=project.analysis.to_dict(),
                    data=data,
                    probes=_probes(project, data),
                    diagnostics=diagnostics,
                    provenance={
                        "solver": "SPIKES owned C++ kernel",
                        "implementation": "strict_fp_dense_mna",
                        "library": str(library.path),
                        "source_sha256": project.source_sha256,
                    },
                )

        assert project.analysis.time_step_s is not None
        assert project.analysis.stop_time_s is not None
        with circuit.solve_transient(
            time_step_s=project.analysis.time_step_s,
            stop_time_s=project.analysis.stop_time_s,
            initialize_from_operating_point=not project.analysis.use_initial_conditions,
            integration_method=integration_method,
        ) as result:
            diagnostics = result.diagnostics()
            if result.status != "converged":
                return _failure(
                    project, result.status, result.message, diagnostics, library.path
                )
            count = result.point_count
            data = {
                "time_s": [result.time(index) for index in range(count)],
                "integration": integration_method,
                "node_voltage_v": {
                    name: [result.node_voltage(index, name) for index in range(count)]
                    for name in node_names
                },
                "element_current_a": {
                    name: [result.element_current(index, name) for index in range(count)]
                    for name in element_names
                },
                "element_power_w": {
                    name: [result.element_power(index, name) for index in range(count)]
                    for name in element_names
                },
            }
            return CircuitResult(
                status="completed",
                model_status="experimental",
                analysis=project.analysis.to_dict(),
                data=data,
                probes=_probes(project, data, count),
                diagnostics=diagnostics | {"points": count},
                provenance={
                    "solver": "SPIKES owned C++ kernel",
                    "implementation": "strict_fp_dense_mna",
                    "integration": integration_method,
                    "owned_cpp_transient": True,
                    "library": str(library.path),
                    "source_sha256": project.source_sha256,
                },
            )


__all__ = ["run_native_project"]
