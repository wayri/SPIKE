"""Execution of parsed SPIKES projects against the owned C++ C ABI."""

from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Any

from .contracts import AnalysisDirective, CircuitProject, CircuitResult, ProbeDescriptor
from .native_abi import NativeCircuit, load_native_library
from .transient_controls import (
    effective_integration_step_s,
    output_times_s,
    retain_transient_outputs,
)


MAX_ANALYTIC_PWL_POINTS = 1_000_000


def _project_measurements(project: CircuitProject, data: dict[str, Any]) -> dict[str, Any]:
    if not project.measurements:
        return {}
    from .measurements import _measurements

    return _measurements(project, data, transient_weighting="time")


def _analytic_sample_times(step_s: float, stop_s: float) -> tuple[float, ...]:
    """Build the bounded fixed grid used to lower analytic sources to native PWL."""

    ratio = stop_s / step_s
    if not math.isfinite(ratio):
        raise ValueError("Analytic source lowering exceeds one million PWL samples.")
    nearest = round(ratio)
    tolerance = 16.0 * math.ulp(max(abs(ratio), 1.0))
    intervals = nearest if abs(ratio - nearest) <= tolerance else math.ceil(ratio)
    if intervals + 1 > MAX_ANALYTIC_PWL_POINTS:
        raise ValueError("Analytic source lowering exceeds one million PWL samples.")
    return tuple(index * step_s for index in range(intervals)) + (stop_s,)


# Retain the focused SIN test helper while the common allocator now serves all
# supported analytic source forms.
_sin_sample_times = _analytic_sample_times


def _populate(circuit: NativeCircuit, project: CircuitProject) -> None:
    for element in project.elements:
        common = (element.name, element.positive_node, element.negative_node)
        if element.kind in {'bsim_bulk','bsim_cmg'}:
            circuit.add_bsim(element.name,element.semiconductor_nodes,family=element.kind,parameters=dict(element.semiconductor_parameters))
            continue
        if element.kind in {'behavioral_voltage_source','behavioral_current_source'}:
            circuit.add_behavioral_source(*common,element.behavioral_expression,voltage_output=element.kind=='behavioral_voltage_source')
            continue
        if element.kind in {'gan_hemt','sic_mosfet'}:
            circuit.add_wbg_fet_electrothermal(element.name,*element.semiconductor_nodes,technology=element.kind,**dict(element.semiconductor_parameters))
            continue
        if element.kind in {'npn_ebers_moll','nmos_level1'}:
            method=circuit.add_bjt_ebers_moll if element.kind=='npn_ebers_moll' else circuit.add_mosfet_level1
            params=dict(element.semiconductor_parameters)
            charge={key.removeprefix('charge_'):params.pop(key) for key in list(params) if key.startswith('charge_')}
            method(element.name,*element.semiconductor_nodes,**params)
            if charge:circuit.set_compact_charge(element.name,**charge)
            continue
        if element.kind in {'vcvs','vccs','ccvs','cccs'}:
            circuit.add_dependent_source(*common,voltage_output=element.kind in {'vcvs','ccvs'},
                control_positive=element.control_positive_node or '0',control_negative=element.control_negative_node or '0',
                control_source=element.control_source_id or '',gain=element.value)
            continue
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
            elif element.waveform.kind == "pwl":
                getattr(circuit, f"add_pwl_{prefix}_source")(
                    *common, element.waveform.points
                )
            elif element.waveform.kind == "sin":
                getattr(circuit, f"add_sine_{prefix}_source")(*common, element.waveform.sine)
            elif element.waveform.kind in {"exp", "sffm"}:
                if project.analysis.mode != "transient":
                    getattr(circuit, f"add_{prefix}_source")(*common, element.value)
                    continue
                assert project.analysis.time_step_s is not None
                assert project.analysis.stop_time_s is not None
                try:
                    bounded_step, _ = effective_integration_step_s(
                        project.analysis.time_step_s,
                        project.analysis.stop_time_s,
                        project.analysis.maximum_time_step_s,
                    )
                except ValueError as exc:
                    raise ValueError(
                        "Analytic source lowering exceeds one million PWL samples."
                    ) from exc
                step = (
                    project.analysis.time_step_s
                    if project.analysis.maximum_time_step_s is None
                    else bounded_step
                )
                stop = project.analysis.stop_time_s
                times = _analytic_sample_times(step, stop)
                getattr(circuit, f"add_pwl_{prefix}_source")(
                    *common,
                    tuple((time, element.waveform.value_at(time)) for time in times),
                )
            else:  # pragma: no cover - SourceWaveform rejects unknown kinds
                raise ValueError(f"Unsupported source waveform {element.waveform.kind}.")
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
        values.update(element.semiconductor_nodes)
        if element.kind in {'behavioral_voltage_source','behavioral_current_source'}:
            from .behavioral import compile_behavioral_expression
            compiled=compile_behavioral_expression(element.behavioral_expression.split('=',1)[1])
            for signal in compiled.signals:
                if signal.kind=='v':values.update((signal.first,signal.second))
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
    maximum_steps: int = 1_000_000,
    adaptive_time_step: bool = False,
    lte_absolute_tolerance: float = 1.0e-6,
    lte_relative_tolerance: float = 1.0e-3,
    minimum_time_step_s: float = 1.0e-15,
    max_rejected_steps: int = 10_000,
) -> CircuitResult:
    """Run a project with one job-local ABI binding and fresh circuits per point."""
    return _run_native_project(
        project, library_path, integration_method=integration_method,
        maximum_steps=maximum_steps, adaptive_time_step=adaptive_time_step,
        lte_absolute_tolerance=lte_absolute_tolerance,
        lte_relative_tolerance=lte_relative_tolerance,
        minimum_time_step_s=minimum_time_step_s,
        max_rejected_steps=max_rejected_steps, _library_state={},
    )


def _run_native_project(
    project: CircuitProject,
    library_path: str | Path,
    *,
    integration_method: str = "hybrid_trapezoidal",
    maximum_steps: int = 1_000_000,
    adaptive_time_step: bool = False,
    lte_absolute_tolerance: float = 1.0e-6,
    lte_relative_tolerance: float = 1.0e-3,
    minimum_time_step_s: float = 1.0e-15,
    max_rejected_steps: int = 10_000,
    _library_state: dict[str, Any],
) -> CircuitResult:
    if type(maximum_steps) is not int or not 1 <= maximum_steps <= 1_000_000:
        raise ValueError("maximum_steps must be an integer from 1 through 1000000")
    if not isinstance(adaptive_time_step, bool):
        raise ValueError("adaptive_time_step must be boolean.")
    normalized_controls: dict[str, float] = {}
    for name, value in (
        ("lte_absolute_tolerance", lte_absolute_tolerance),
        ("lte_relative_tolerance", lte_relative_tolerance),
        ("minimum_time_step_s", minimum_time_step_s),
    ):
        if isinstance(value, bool):
            raise ValueError(f"{name} must be a positive finite number.")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a positive finite number.") from exc
        if not math.isfinite(number) or number <= 0.0:
            raise ValueError(f"{name} must be a positive finite number.")
        normalized_controls[name] = number
    lte_absolute_tolerance = normalized_controls["lte_absolute_tolerance"]
    lte_relative_tolerance = normalized_controls["lte_relative_tolerance"]
    minimum_time_step_s = normalized_controls["minimum_time_step_s"]
    try:
        rejected_steps = int(max_rejected_steps)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("max_rejected_steps must be a positive integer.") from exc
    if (
        isinstance(max_rejected_steps, bool)
        or rejected_steps != max_rejected_steps
        or rejected_steps <= 0
    ):
        raise ValueError("max_rejected_steps must be a positive integer.")
    max_rejected_steps = rejected_steps
    nondefault_adaptive_controls = (
        lte_absolute_tolerance != 1.0e-6
        or lte_relative_tolerance != 1.0e-3
        or minimum_time_step_s != 1.0e-15
        or max_rejected_steps != 10_000
    )
    if project.analysis.mode != "transient" and (
        adaptive_time_step or nondefault_adaptive_controls
    ):
        raise ValueError("Adaptive transient controls require a transient analysis.")
    if nondefault_adaptive_controls and not adaptive_time_step:
        raise ValueError("Non-default adaptive controls require adaptive_time_step=True.")
    normalized_method = str(integration_method).strip().lower()
    reported_method = (
        "radau_iia3" if normalized_method == "radau_iia3" else integration_method
    )
    if adaptive_time_step and normalized_method == "backward_euler":
        raise ValueError("Adaptive time stepping requires hybrid_trapezoidal or bdf2 integration.")
    if adaptive_time_step and normalized_method == "radau_iia3":
        raise ValueError("Radau IIA3 does not support adaptive time stepping.")
    if adaptive_time_step and project.analysis.mode == "transient":
        assert project.analysis.time_step_s is not None
        assert project.analysis.stop_time_s is not None
        admission_step, _ = effective_integration_step_s(
            project.analysis.time_step_s,
            project.analysis.stop_time_s,
            project.analysis.maximum_time_step_s,
        )
        if minimum_time_step_s > admission_step:
            raise ValueError(
                "minimum_time_step_s must not exceed the effective integration step."
            )
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
            point_result = _run_native_project(
                point_project,
                library_path,
                integration_method=integration_method,
                maximum_steps=maximum_steps,
                adaptive_time_step=adaptive_time_step,
                lte_absolute_tolerance=lte_absolute_tolerance,
                lte_relative_tolerance=lte_relative_tolerance,
                minimum_time_step_s=minimum_time_step_s,
                max_rejected_steps=max_rejected_steps,
                _library_state=_library_state,
            )
            parameters = {name: value for name, value in variant.parameters}
            if point_result.status != "completed":
                return CircuitResult(
                    status="failed",
                    model_status=point_result.model_status,
                    analysis=project.analysis.to_dict(),
                    diagnostics=dict(point_result.diagnostics) | {"completed_step_variants": len(point_results)},
                    issues=tuple(point_result.issues) + ({
                        "code": "SPIKES_STEP_POINT_FAILED",
                        "severity": "error",
                        "message": "A nested STEP variant did not complete.",
                        "parameters": parameters,
                    },),
                    provenance=dict(point_result.provenance) | {
                        "step_parameters": parameters,
                        "step_orchestration": "deterministic_cartesian_owned_cpp",
                    },
                )
            point_results.append({
                "parameters": parameters,
                "data": dict(point_result.data),
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
            status="completed",
            model_status="experimental",
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
                "solver": "SPIKES owned C++ kernel",
                "source_sha256": project.source_sha256,
                "step_orchestration": "deterministic_cartesian_owned_cpp",
                "library": str(Path(library_path).resolve()),
            },
        )

    if project.analysis.mode not in {"operating_point", "dc_sweep", "transient"}:
        raise ValueError(
            f"Owned native runner does not support {project.analysis.mode} analysis."
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
                measurements=(),
            )
            point_result = _run_native_project(
                point_project,
                library_path,
                integration_method=integration_method,
                maximum_steps=maximum_steps,
                adaptive_time_step=adaptive_time_step,
                lte_absolute_tolerance=lte_absolute_tolerance,
                lte_relative_tolerance=lte_relative_tolerance,
                minimum_time_step_s=minimum_time_step_s,
                max_rejected_steps=max_rejected_steps,
                _library_state=_library_state,
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
            measurements=_project_measurements(project, data),
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
    library = _library_state.get("library")
    if library is None:
        library = load_native_library(library_path)
        _library_state["library"] = library
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
                    measurements=_project_measurements(project, data),
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
        bounded_step, integration_point_limit = effective_integration_step_s(
            project.analysis.time_step_s,
            project.analysis.stop_time_s,
            project.analysis.maximum_time_step_s,
        )
        integration_step = (
            project.analysis.time_step_s
            if project.analysis.maximum_time_step_s is None
            else bounded_step
        )
        if integration_point_limit - 1 > maximum_steps:
            raise ValueError(
                "Transient integration grid exceeds maximum_steps before native allocation."
            )
        with circuit.solve_transient(
            time_step_s=integration_step,
            stop_time_s=project.analysis.stop_time_s,
            initialize_from_operating_point=not project.analysis.use_initial_conditions,
            integration_method=integration_method,
            max_steps=maximum_steps,
            adaptive_time_step=adaptive_time_step,
            lte_absolute_tolerance=lte_absolute_tolerance,
            lte_relative_tolerance=lte_relative_tolerance,
            minimum_time_step_s=minimum_time_step_s,
            max_rejected_steps=max_rejected_steps,
        ) as result:
            diagnostics = result.diagnostics()
            if result.status != "converged":
                return _failure(
                    project, result.status, result.message, diagnostics, library.path
                )
            integration_count = result.point_count
            integration_data = {
                "time_s": result.time_values(),
                "integration": reported_method,
                "node_voltage_v": {
                    name: result.node_voltage_values(name)
                    for name in node_names
                },
                "element_current_a": {
                    name: result.element_current_values(name)
                    for name in element_names
                },
                "element_power_w": {
                    name: result.element_power_values(name)
                    for name in element_names
                },
            }
            legacy_default_grid = (
                not adaptive_time_step
                and project.analysis.start_time_s == 0.0
                and project.analysis.maximum_time_step_s is None
            )
            if legacy_default_grid:
                data = integration_data
                count = integration_count
            else:
                target_times = output_times_s(
                    project.analysis.time_step_s,
                    project.analysis.start_time_s,
                    project.analysis.stop_time_s,
                )
                data = retain_transient_outputs(integration_data, target_times)
                count = len(target_times)
            return CircuitResult(
                status="completed",
                model_status="experimental",
                analysis=project.analysis.to_dict(),
                data=data,
                probes=_probes(project, data, count),
                measurements=_project_measurements(project, integration_data),
                diagnostics=diagnostics | {
                    "points": count,
                    "integration_points": integration_count,
                    "effective_integration_step_s": integration_step,
                },
                provenance={
                    "solver": "SPIKES owned C++ kernel",
                    "implementation": "strict_fp_dense_mna",
                    "integration": reported_method,
                    "owned_cpp_transient": True,
                    "transient_controls": {
                        "integration_origin_s": 0.0,
                        "output_start_time_s": project.analysis.start_time_s,
                        "output_time_step_s": project.analysis.time_step_s,
                        "requested_maximum_time_step_s": project.analysis.maximum_time_step_s,
                        "effective_integration_step_s": integration_step,
                        "adaptive_time_step": adaptive_time_step,
                        "minimum_time_step_s": minimum_time_step_s,
                        "lte_absolute_tolerance": lte_absolute_tolerance,
                        "lte_relative_tolerance": lte_relative_tolerance,
                        "max_rejected_steps": max_rejected_steps,
                        "output_sampling": (
                            "legacy_native_integration_grid"
                            if legacy_default_grid
                            else (
                                "linear_from_adaptive_integration_grid"
                                if adaptive_time_step
                                else "linear_from_fixed_integration_grid"
                            )
                        ),
                        "final_stop_included": True,
                        **({
                            "source_breakpoint_samples":
                                "left_limit_at_actual_source_jumps",
                        } if normalized_method == "radau_iia3" else {}),
                    },
                    **({
                        "analytic_source_lowering": "fixed_step_pwl_samples",
                        "analytic_source_sampling_grid": "integration_grid",
                        "analytic_source_sample_semantics": (
                            "exact_at_requested_tran_times"
                            if project.analysis.maximum_time_step_s is None
                            else "exact_at_integration_times"
                        ),
                        **{
                            f"{kind}_source_lowering": "fixed_step_pwl_samples"
                            for kind in ("exp", "sffm")
                            if any(
                                element.waveform is not None and element.waveform.kind == kind
                                for element in project.elements
                            )
                        },
                    } if any(
                        element.waveform is not None
                        and element.waveform.kind in {"exp", "sffm"}
                        for element in project.elements
                    ) else {}),
                    **({"sin_source_lowering": "native_analytic",
                        "sin_source_sample_semantics": "analytic_at_internal_solve_times"}
                       if any(element.waveform is not None and element.waveform.kind == "sin"
                              for element in project.elements) else {}),
                    "library": str(library.path),
                    "source_sha256": project.source_sha256,
                },
            )


__all__ = ["run_native_project"]
