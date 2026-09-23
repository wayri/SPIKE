"""Versioned PWM converter study orchestration and engineering analytics.

The workflow composes a reviewed SPICE workspace, optionally inserts reviewed
PEEC RLCG sections, runs ngspice in its existing isolated adapter, computes
windowed converter metrics, and hands explicit losses to the compact thermal
model. It is staged coupling, not an iterative field/circuit solution.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import time
from typing import Any, Dict, Iterable, List, Sequence

from .contracts import AnalysisSpec, DesignIR
from .ngspice_plugin import NgspicePlugin
from .peec_spice_export import run_staged_hybrid_cosimulation
from .spice_workspace import compose_spice_workspace, validate_spice_workspace
from .thermal import ThermalScenario, estimate_compact_thermal


CONVERTER_STUDY_CONTRACT = "spike/converter-study/v1"
CONVERTER_STUDY_RESULT_CONTRACT = "spike/converter-study-result/v1"
CONVERTER_STUDY_VALIDATION_CONTRACT = "spike/converter-study-validation/v1"
SUPPORTED_TOPOLOGIES = {
    "buck", "boost", "buck_boost", "flyback", "forward", "half_bridge",
    "full_bridge", "push_pull", "cuk", "sepic", "custom_pwm",
}
REQUIRED_BINDINGS = (
    "input_voltage", "input_current", "output_voltage", "output_current",
)
_STATUS_RANK = {
    "validated": 0,
    "solver_dependent": 1,
    "approximate": 2,
    "experimental": 3,
    "unvalidated": 4,
    "unsupported": 5,
    "failed": 6,
}


def _issue(code: str, message: str, *, severity: str = "error", path: str = "") -> Dict[str, str]:
    return {"code": code, "severity": severity, "message": message, "path": path}


def _finite(value: Any, *, positive: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or (positive and number <= 0):
        return None
    return number


def _model_status(*values: Any) -> str:
    normalized = [str(value or "unvalidated").strip().lower() for value in values]
    return max(normalized, key=lambda value: _STATUS_RANK.get(value, 4))


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def converter_capabilities() -> Dict[str, Any]:
    """Return explicit execution and future capability gates."""

    return {
        "contract": "spike/converter-study-capabilities/v1",
        "available": [
            "reviewed_visual_spice_workspace",
            "structured_pwm_source_materialization",
            "ngspice_transient_execution",
            "reviewed_peec_rlcg_insertion",
            "efficiency_ripple_inrush_analytics",
            "component_stress_analytics",
            "compact_thermal_loss_handoff",
        ],
        "gated": {
            "iterative_spice_fea": "A validated field/circuit convergence loop is not implemented.",
            "bode_loop_gain": "A reviewed injection source, probe definition, and loop-gain extraction contract is required.",
            "switching_loss_inference": "Device loss requires explicit voltage/current or power-vector bindings.",
            "thermal_cfd": "Use the separate OpenFOAM workflow after a validated multi-region case is available.",
        },
        "coupling": "one_way_staged",
    }


def materialize_converter_workspace(study: Dict[str, Any]) -> Dict[str, Any]:
    """Compile structured PWM source settings into a copied SPICE workspace."""

    workspace = deepcopy(study.get("workspace", {}))
    switching = study.get("switching", {})
    sources = switching.get("sources", []) if isinstance(switching, dict) else []
    if not isinstance(sources, list):
        return workspace
    models = {
        str(model.get("id", "")): model
        for model in workspace.get("models", [])
        if isinstance(model, dict)
    }
    base_frequency = _finite(switching.get("frequency_hz"), positive=True)
    base_duty = _finite(switching.get("duty_cycle"))
    for source in sources:
        if not isinstance(source, dict):
            continue
        model = models.get(str(source.get("model_id", "")))
        if not model or model.get("primitive") not in {"voltage_source", "current_source"}:
            continue
        frequency = _finite(source.get("frequency_hz"), positive=True) or base_frequency
        duty = _finite(source.get("duty_cycle"))
        if duty is None:
            duty = base_duty
        if frequency is None or duty is None or not 0 < duty < 1:
            continue
        period = 1.0 / frequency
        delay = _finite(source.get("delay_s", 0))
        rise = _finite(source.get("rise_s", 0))
        fall = _finite(source.get("fall_s", 0))
        phase = _finite(source.get("phase_deg", 0))
        low = _finite(source.get("low", 0))
        high = _finite(source.get("high"))
        on_time = _finite(source.get("on_time_s"))
        if on_time is None:
            on_time = period * duty
        if None in {delay, rise, fall, phase, low, high}:
            continue
        phase_delay = period * (phase % 360.0) / 360.0
        model["value"] = (
            f"PULSE({low:.12g} {high:.12g} {(delay + phase_delay):.12g} "
            f"{rise:.12g} {fall:.12g} {on_time:.12g} {period:.12g})"
        )
    return workspace


def validate_converter_study(study: Dict[str, Any], design: DesignIR) -> Dict[str, Any]:
    """Validate converter intent without executing any solver."""

    issues: List[Dict[str, str]] = []
    warnings: List[Dict[str, str]] = []
    if not isinstance(study, dict) or study.get("contract") != CONVERTER_STUDY_CONTRACT:
        issues.append(_issue("CONVERTER_CONTRACT_INVALID", f"Expected {CONVERTER_STUDY_CONTRACT}."))
        return {
            "contract": CONVERTER_STUDY_VALIDATION_CONTRACT,
            "valid": False,
            "can_run": False,
            "issues": issues,
            "warnings": warnings,
            "capabilities": converter_capabilities(),
        }

    if not str(study.get("study_id", "")).strip():
        issues.append(_issue("CONVERTER_STUDY_ID_REQUIRED", "A stable study_id is required.", path="study_id"))
    topology = str(study.get("topology", "")).strip().lower()
    if topology not in SUPPORTED_TOPOLOGIES:
        issues.append(_issue("CONVERTER_TOPOLOGY_UNSUPPORTED", "Select a supported topology or custom_pwm.", path="topology"))
    switching = study.get("switching", {})
    if not isinstance(switching, dict) or _finite(switching.get("frequency_hz"), positive=True) is None:
        issues.append(_issue("CONVERTER_SWITCHING_FREQUENCY_INVALID", "Switching frequency must be finite and positive.", path="switching.frequency_hz"))
    duty = _finite(switching.get("duty_cycle")) if isinstance(switching, dict) else None
    if duty is None or not 0 < duty < 1:
        issues.append(_issue("CONVERTER_DUTY_CYCLE_INVALID", "Duty cycle must be between zero and one.", path="switching.duty_cycle"))
    dead_time = _finite(switching.get("dead_time_s", 0)) if isinstance(switching, dict) else None
    if dead_time is None or dead_time < 0:
        issues.append(_issue("CONVERTER_DEAD_TIME_INVALID", "Dead time must be finite and non-negative.", path="switching.dead_time_s"))

    raw_workspace = study.get("workspace", {})
    sources = switching.get("sources", []) if isinstance(switching, dict) else []
    if not isinstance(sources, list):
        issues.append(_issue("CONVERTER_PWM_SOURCES_INVALID", "switching.sources must be an array.", path="switching.sources"))
        sources = []
    models = {
        str(model.get("id", "")): model
        for model in raw_workspace.get("models", [])
        if isinstance(raw_workspace, dict) and isinstance(model, dict)
    }
    for index, source in enumerate(sources):
        path = f"switching.sources[{index}]"
        if not isinstance(source, dict):
            issues.append(_issue("CONVERTER_PWM_SOURCE_INVALID", "Each PWM source must be an object.", path=path))
            continue
        model = models.get(str(source.get("model_id", "")))
        if not model or model.get("primitive") not in {"voltage_source", "current_source"}:
            issues.append(_issue("CONVERTER_PWM_SOURCE_MODEL_INVALID", "PWM source model_id must reference a primitive voltage or current source.", path=f"{path}.model_id"))
        for field in ("delay_s", "rise_s", "fall_s"):
            value = _finite(source.get(field, 0))
            if value is None or value < 0:
                issues.append(_issue("CONVERTER_PWM_TIMING_INVALID", f"{field} must be finite and non-negative.", path=f"{path}.{field}"))
        source_frequency = _finite(source.get("frequency_hz"), positive=True) or _finite(switching.get("frequency_hz"), positive=True)
        source_duty = _finite(source.get("duty_cycle"))
        if source_duty is None:
            source_duty = duty
        period = 1.0 / source_frequency if source_frequency else None
        on_time = _finite(source.get("on_time_s"))
        if on_time is not None and (on_time <= 0 or period is not None and on_time >= period):
            issues.append(_issue("CONVERTER_PWM_ON_TIME_INVALID", "on_time_s must be positive and shorter than the source period.", path=f"{path}.on_time_s"))
        if _finite(source.get("high")) is None or _finite(source.get("low", 0)) is None:
            issues.append(_issue("CONVERTER_PWM_LEVEL_INVALID", "PWM low and high levels must be finite.", path=path))
        if source_duty is None or not 0 < source_duty < 1:
            issues.append(_issue("CONVERTER_PWM_DUTY_INVALID", "PWM duty cycle must be between zero and one.", path=f"{path}.duty_cycle"))

    workspace = materialize_converter_workspace(study)
    workspace_validation = validate_spice_workspace(workspace, design)
    issues.extend(workspace_validation.get("issues", []))
    warnings.extend(workspace_validation.get("warnings", []))
    analysis = workspace.get("analysis", {}) if isinstance(workspace, dict) else {}
    if analysis.get("mode") != "transient":
        issues.append(_issue("CONVERTER_TRANSIENT_REQUIRED", "Converter studies require a transient SPICE workspace.", path="workspace.analysis.mode"))

    bindings = study.get("waveform_bindings", {})
    if not isinstance(bindings, dict):
        bindings = {}
        issues.append(_issue("CONVERTER_BINDINGS_INVALID", "waveform_bindings must be an object.", path="waveform_bindings"))
    for name in REQUIRED_BINDINGS:
        if not str(bindings.get(name, "")).strip():
            issues.append(_issue("CONVERTER_WAVEFORM_BINDING_REQUIRED", f"Bind the {name} ngspice vector explicitly.", path=f"waveform_bindings.{name}"))

    measurement = study.get("measurement_window", {})
    start = _finite(measurement.get("start_s")) if isinstance(measurement, dict) else None
    stop = _finite(measurement.get("stop_s")) if isinstance(measurement, dict) else None
    transient_stop = _finite(analysis.get("stop_time_s")) if isinstance(analysis, dict) else None
    if start is None or stop is None or start < 0 or stop <= start:
        issues.append(_issue("CONVERTER_MEASUREMENT_WINDOW_INVALID", "Set a finite measurement window with 0 <= start < stop.", path="measurement_window"))
    elif transient_stop is not None and stop > transient_stop:
        issues.append(_issue("CONVERTER_MEASUREMENT_WINDOW_OUTSIDE_RUN", "Measurement stop exceeds the transient stop time.", path="measurement_window.stop_s"))

    peec = study.get("peec", {})
    if peec and (not isinstance(peec, dict) or not isinstance(peec.get("mappings"), list) or not peec.get("mappings")):
        issues.append(_issue("CONVERTER_PEEC_MAPPING_REQUIRED", "PEEC coupling requires reviewed endpoint mappings.", path="peec.mappings"))
    for index, loss in enumerate(study.get("loss_bindings", [])):
        path = f"loss_bindings[{index}]"
        if not isinstance(loss, dict) or not str(loss.get("id", "")).strip():
            issues.append(_issue("CONVERTER_LOSS_BINDING_INVALID", "Each loss binding requires an ID.", path=path))
            continue
        has_power = bool(str(loss.get("power_vector", "")).strip())
        has_pair = bool(str(loss.get("voltage_vector", "")).strip() and str(loss.get("current_vector", "")).strip())
        if not has_power and not has_pair:
            issues.append(_issue("CONVERTER_LOSS_VECTORS_REQUIRED", "Bind a power vector or voltage/current vector pair.", path=path))
    if not study.get("loss_bindings"):
        warnings.append(_issue("CONVERTER_DEVICE_LOSS_BINDINGS_MISSING", "Device stress, loss breakdown, and thermal handoff will be incomplete.", severity="warning", path="loss_bindings"))

    return {
        "contract": CONVERTER_STUDY_VALIDATION_CONTRACT,
        "valid": not issues,
        "can_run": not issues,
        "issues": issues,
        "warnings": warnings,
        "workspace": workspace_validation,
        "materialized_pwm_sources": len(sources),
        "capabilities": converter_capabilities(),
    }


def _real_vector(vectors: Dict[str, Any], name: str) -> List[float]:
    values = vectors.get(name, [])
    if not isinstance(values, list):
        return []
    output: List[float] = []
    for value in values:
        if isinstance(value, dict):
            return []
        number = _finite(value)
        if number is None:
            return []
        output.append(number)
    return output


def _window_indices(time_s: Sequence[float], start_s: float, stop_s: float) -> List[int]:
    return [index for index, value in enumerate(time_s) if start_s <= value <= stop_s]


def _time_average(values: Sequence[float], times_s: Sequence[float], *, square: bool = False) -> float:
    if len(values) < 2 or len(values) != len(times_s) or times_s[-1] <= times_s[0]:
        transformed = [value * value if square else value for value in values]
        return sum(transformed) / len(transformed)
    integral = 0.0
    for index in range(1, len(values)):
        left = values[index - 1] * values[index - 1] if square else values[index - 1]
        right = values[index] * values[index] if square else values[index]
        integral += 0.5 * (left + right) * (times_s[index] - times_s[index - 1])
    return integral / (times_s[-1] - times_s[0])


def _statistics(values: Sequence[float], times_s: Sequence[float] = ()) -> Dict[str, float]:
    if not values:
        return {}
    mean = _time_average(values, times_s)
    centered = [value - mean for value in values]
    return {
        "minimum": min(values),
        "maximum": max(values),
        "mean": mean,
        "rms": math.sqrt(max(0.0, _time_average(values, times_s, square=True))),
        "ripple_peak_to_peak": max(values) - min(values),
        "ripple_rms": math.sqrt(max(0.0, _time_average(centered, times_s, square=True))),
    }


def _bound_series(vectors: Dict[str, Any], bindings: Dict[str, Any], indices: Sequence[int], name: str) -> List[float]:
    vector = _real_vector(vectors, str(bindings.get(name, "")))
    if not vector or max(indices, default=-1) >= len(vector):
        raise ValueError(f"Bound ngspice vector is missing or incomplete: {name} -> {bindings.get(name, '')}")
    polarity = _finite(bindings.get(f"{name}_polarity", 1))
    if polarity not in {-1.0, 1.0}:
        raise ValueError(f"{name}_polarity must be -1 or 1.")
    return [vector[index] * polarity for index in indices]


def _converter_analytics(study: Dict[str, Any], circuit: Dict[str, Any]) -> Dict[str, Any]:
    vectors = circuit.get("fields", {}).get("waveforms", {})
    time_s = _real_vector(vectors, "time")
    window = study["measurement_window"]
    indices = _window_indices(time_s, float(window["start_s"]), float(window["stop_s"]))
    if len(indices) < 2:
        raise ValueError("The measurement window contains fewer than two transient samples.")
    bindings = study["waveform_bindings"]
    vin = _bound_series(vectors, bindings, indices, "input_voltage")
    iin = _bound_series(vectors, bindings, indices, "input_current")
    vout = _bound_series(vectors, bindings, indices, "output_voltage")
    iout = _bound_series(vectors, bindings, indices, "output_current")
    pin = [voltage * current for voltage, current in zip(vin, iin)]
    pout = [voltage * current for voltage, current in zip(vout, iout)]
    window_times = [time_s[index] for index in indices]
    pin_mean = _time_average(pin, window_times)
    pout_mean = _time_average(pout, window_times)
    loss = pin_mean - pout_mean
    efficiency = pout_mean / pin_mean * 100 if pin_mean > 0 else None
    output_stats = _statistics(vout, window_times)
    input_current_stats = _statistics(iin, window_times)
    return {
        "measurement_window": {**window, "sample_count": len(indices)},
        "statistics_method": "time_weighted_trapezoidal",
        "input_voltage_v": _statistics(vin, window_times),
        "input_current_a": input_current_stats,
        "output_voltage_v": output_stats,
        "output_current_a": _statistics(iout, window_times),
        "input_power_w": _statistics(pin, window_times),
        "output_power_w": _statistics(pout, window_times),
        "average_input_power_w": pin_mean,
        "average_output_power_w": pout_mean,
        "average_loss_w": loss,
        "efficiency_percent": efficiency,
        "output_ripple_peak_to_peak_v": output_stats["ripple_peak_to_peak"],
        "output_ripple_rms_v": output_stats["ripple_rms"],
        "input_inrush_peak_a": max((abs(value) for value in iin), default=0.0),
    }


def _loss_analytics(study: Dict[str, Any], vectors: Dict[str, Any]) -> List[Dict[str, Any]]:
    time_s = _real_vector(vectors, "time")
    window = study["measurement_window"]
    indices = _window_indices(time_s, float(window["start_s"]), float(window["stop_s"]))
    window_times = [time_s[index] for index in indices]
    losses = []
    for binding in study.get("loss_bindings", []):
        if binding.get("power_vector"):
            power = _bound_series(vectors, {"power": binding["power_vector"], "power_polarity": binding.get("polarity", 1)}, indices, "power")
        else:
            voltage = _bound_series(vectors, {"voltage": binding["voltage_vector"], "voltage_polarity": 1}, indices, "voltage")
            current = _bound_series(vectors, {"current": binding["current_vector"], "current_polarity": binding.get("polarity", 1)}, indices, "current")
            power = [v * i for v, i in zip(voltage, current)]
        stats = _statistics(power, window_times)
        losses.append({
            "id": str(binding["id"]),
            "reference": str(binding.get("reference", binding["id"])),
            "average_power_w": stats.get("mean", 0.0),
            "peak_absolute_power_w": max((abs(value) for value in power), default=0.0),
            "statistics_w": stats,
            "thermal": deepcopy(binding.get("thermal", {})),
            "ratings": deepcopy(binding.get("ratings", {})),
        })
    return losses


def _engineering_issues(study: Dict[str, Any], analytics: Dict[str, Any]) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    pin = float(analytics["average_input_power_w"])
    pout = float(analytics["average_output_power_w"])
    loss = float(analytics["average_loss_w"])
    if pin <= 0 or pout < 0:
        issues.append(_issue(
            "CONVERTER_POWER_DIRECTION_INVALID",
            "Average input power must be positive and output power non-negative; review vector polarities and the measurement window.",
            severity="warning",
        ))
    tolerance = max(abs(pin), abs(pout), 1.0) * 1e-6
    if loss < -tolerance:
        issues.append(_issue(
            "CONVERTER_ENERGY_BALANCE_NEGATIVE_LOSS",
            "Average output power exceeds input power; review current directions, omitted rails, controlled sources, and model energy storage.",
            severity="warning",
        ))
    limits = study.get("limits", {})
    if not isinstance(limits, dict):
        return issues
    checks = (
        ("minimum_efficiency_percent", analytics.get("efficiency_percent"), lambda actual, limit: actual < limit, "CONVERTER_EFFICIENCY_LIMIT", "%"),
        ("maximum_output_ripple_v", analytics.get("output_ripple_peak_to_peak_v"), lambda actual, limit: actual > limit, "CONVERTER_RIPPLE_LIMIT", "V peak-to-peak"),
        ("maximum_input_inrush_a", analytics.get("input_inrush_peak_a"), lambda actual, limit: actual > limit, "CONVERTER_INRUSH_LIMIT", "A"),
    )
    for field, actual, predicate, code, unit in checks:
        limit = _finite(limits.get(field), positive=True)
        if limit is not None and actual is not None and predicate(float(actual), limit):
            issues.append(_issue(code, f"Measured {field} limit violation: {float(actual):.6g} {unit}; limit {limit:.6g} {unit}.", severity="warning", path=f"limits.{field}"))
    return issues


def _thermal_handoff(study: Dict[str, Any], losses: Iterable[Dict[str, Any]]) -> Dict[str, Any] | None:
    scenario_data = study.get("thermal_scenario")
    if not isinstance(scenario_data, dict):
        return None
    scenario_data = deepcopy(scenario_data)
    scenario_data.setdefault("contract", "spike/thermal/v1")
    scenario_data.setdefault("scenario_id", f"{study.get('study_id', 'converter')}-thermal")
    sources = list(scenario_data.get("heat_sources", []))
    for loss in losses:
        thermal = loss.get("thermal", {})
        if not isinstance(thermal, dict) or _finite(thermal.get("theta_ja_c_per_w"), positive=True) is None:
            continue
        sources.append({
            "id": str(loss["id"]),
            "power_w": max(0.0, float(loss["average_power_w"])),
            "theta_ja_c_per_w": float(thermal["theta_ja_c_per_w"]),
            "thermal_capacitance_j_per_c": float(thermal.get("thermal_capacitance_j_per_c", 0) or 0),
            "source": "converter_loss_binding",
        })
    scenario_data["heat_sources"] = sources
    return estimate_compact_thermal(ThermalScenario(**scenario_data))


def run_converter_study(
    design: DesignIR,
    study: Dict[str, Any],
    extraction_result: Dict[str, Any] | None = None,
    *,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    """Execute a converter study through reviewed, staged solver handoffs."""

    started = time.perf_counter()

    def finished(payload: Dict[str, Any]) -> Dict[str, Any]:
        payload["elapsed_seconds"] = time.perf_counter() - started
        return payload

    validation = validate_converter_study(study, design)
    workspace = materialize_converter_workspace(study)
    execution_study = deepcopy(study)
    execution_study["workspace"] = workspace
    base = {
        "contract": CONVERTER_STUDY_RESULT_CONTRACT,
        "study_id": str(study.get("study_id", "")),
        "topology": str(study.get("topology", "")),
        "validation": validation,
        "capabilities": converter_capabilities(),
        "provenance": {
            "orchestrator": "python.spike_core.converter_study",
            "study_sha256": _digest(study),
            "design_sha256": _digest(design.to_dict()),
            "coupling": "one_way_staged",
        },
    }
    if not validation["can_run"]:
        return finished({**base, "status": "blocked", "model_status": "unsupported", "stages": [], "issues": validation["issues"] + validation["warnings"]})

    peec = study.get("peec", {})
    if peec:
        if not extraction_result:
            return finished({**base, "status": "blocked", "model_status": "unsupported", "stages": [], "issues": [_issue("CONVERTER_PEEC_RESULT_REQUIRED", "The study requests PEEC coupling but no extraction result was supplied.")]})
        hybrid = run_staged_hybrid_cosimulation(
            design,
            extraction_result,
            workspace,
            peec["mappings"],
            timeout_seconds=timeout_seconds,
        )
        circuit = hybrid.get("result") or {}
        circuit_stage = {"id": "circuit", "status": hybrid.get("status", "failed"), "result": circuit, "handoff": hybrid.get("import")}
    else:
        preview = compose_spice_workspace(workspace, design)
        spec = AnalysisSpec(
            analysis_id=f"{study['study_id']}-ngspice",
            mode="spice",
            solver_id="spike.ngspice",
            formulation="explicit_converter_netlist",
            options={
                "spice_netlist": preview.get("netlist", ""),
                "timeout_seconds": max(1, min(int(timeout_seconds), 3600)),
                "spice_overlay_bindings": workspace.get("overlay_bindings", []),
                "component_stress_bindings": workspace.get("component_stress_bindings", []),
            },
        )
        circuit = NgspicePlugin().run(design, spec).to_dict()
        circuit_stage = {"id": "circuit", "status": circuit.get("status", "failed"), "netlist_preview": preview, "result": circuit}

    if circuit.get("status") != "completed":
        return finished({
            **base,
            "status": circuit.get("status", "failed"),
            "model_status": circuit.get("model_status", "failed"),
            "stages": [circuit_stage],
            "issues": validation["warnings"] + circuit.get("issues", []),
        })
    try:
        analytics = _converter_analytics(execution_study, circuit)
        losses = _loss_analytics(execution_study, circuit.get("fields", {}).get("waveforms", {}))
    except ValueError as exc:
        return finished({
            **base,
            "status": "failed",
            "model_status": "failed",
            "stages": [circuit_stage],
            "issues": validation["warnings"] + [_issue("CONVERTER_ANALYTICS_BINDING_FAILED", str(exc))],
        })

    bound_loss = sum(max(0.0, float(item["average_power_w"])) for item in losses)
    analytics["bound_component_loss_w"] = bound_loss
    analytics["unallocated_loss_w"] = float(analytics["average_loss_w"]) - bound_loss
    thermal = _thermal_handoff(execution_study, losses)
    stages = [circuit_stage, {"id": "analytics", "status": "completed"}]
    statuses = [circuit.get("model_status", "solver_dependent")]
    if thermal:
        stages.append({"id": "thermal", "status": thermal["status"], "result": thermal})
        statuses.append(thermal["model_status"])
    issues = validation["warnings"] + circuit.get("issues", []) + _engineering_issues(study, analytics)
    issues.append(_issue(
        "CONVERTER_STAGED_COUPLING",
        "Electrical, extracted interconnect, and compact thermal stages are one-way; temperatures do not feed updated device or conductor parameters back into ngspice.",
        severity="warning",
    ))
    return finished({
        **base,
        "status": "completed",
        "model_status": _model_status(*statuses),
        "stages": stages,
        "summary": analytics,
        "component_losses": losses,
        "thermal": thermal,
        "waveforms": circuit.get("fields", {}).get("waveforms", {}),
        "visualization": circuit.get("fields", {}).get("visualization", {}),
        "component_stress": circuit.get("networks", {}).get("component_stress", []),
        "issues": issues,
    })


__all__ = [
    "CONVERTER_STUDY_CONTRACT",
    "CONVERTER_STUDY_RESULT_CONTRACT",
    "converter_capabilities",
    "materialize_converter_workspace",
    "run_converter_study",
    "validate_converter_study",
]
