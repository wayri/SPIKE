"""Geometry-derived quasi-static PEEC R/L/C transient solver.

Resistance and partial inductance are extracted from the connected conductor
mesh.  Optional distributed shunt capacitance is estimated from the imported
stackup and an explicit return conductor (or a clearly reported implicit local
reference).  The capacitance model is a quasi-static single-reference
approximation; it is not a full-wave field solution.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, log, pi, sqrt
from time import perf_counter
from typing import Any, Dict, Iterable, List, Tuple
import warnings

import numpy as np
from scipy.linalg import LinAlgWarning, lu_factor, lu_solve

from .contracts import AnalysisResult, AnalysisSpec, DesignIR, ValidationIssue
from .hybrid_mesh import HybridMesh, build_hybrid_mesh, nearest_mesh_node
from .numerics import assess_symmetric_positive_semidefinite
from .peec_plugin import _dense, _dielectric_epsilon, _make_native_solver, native_available
from .quasistatic_capacitance import estimate_line_capacitance_per_m
from .spatial_sampling import stratified_sample_records


DENSE_TRANSIENT_BYTES_PER_BRANCH_SQUARED = 160
TRANSIENT_WORKSPACE_FRACTION = 0.65
MAX_ABSOLUTE_STATE_MAGNITUDE = 1e12
EPSILON_0_F_M = 8.8541878128e-12
LIGHT_SPEED_M_S = 299792458.0


@dataclass(frozen=True)
class TransientSettings:
    stop_time_s: float
    requested_time_step_s: float
    time_step_s: float
    internal_steps: int
    requested_output_decimation: int
    output_decimation: int
    output_decimation_mode: str
    playback_fps: int
    initial_condition: str
    time_step_mode: str
    max_internal_steps: int
    max_output_frames: int
    max_branches: int
    configured_max_branches: int | None
    memory_admitted_max_branches: int
    max_solver_time_s: float
    memory_budget_bytes: int
    capacitance_model: str
    visual_sample_limit: int


def recommend_time_step_s(spec: AnalysisSpec) -> float:
    """Recommend a bounded integration step from the requested waveforms.

    This is an excitation-bandwidth recommendation, not a full-wave CFL limit.
    A later solver summary reports the fastest extracted LC characteristic time
    so users can decide whether a shorter, dedicated run is required.
    """

    value = spec.transient or {}
    stop_time = float(value.get("stop_time_s", 1e-3))
    candidates = [stop_time / 1000.0]
    for terminal in [*spec.sources, *spec.loads]:
        profile = _profile(terminal)
        kind = str(profile.get("kind", "constant")).lower()
        if kind in {"step", "pulse"}:
            for key in ("rise_time_s", "fall_time_s"):
                edge = float(profile.get(key, 0) or 0)
                if edge > 0:
                    candidates.append(edge / 10.0)
        elif kind == "piecewise_linear":
            try:
                points = _pwl_points(profile.get("points", profile.get("data", [])))
            except (TypeError, ValueError):
                continue
            candidates.extend((right[0] - left[0]) / 10.0 for left, right in zip(points, points[1:]))
    return max(min(candidates), stop_time * 1e-12)


def transient_settings(spec: AnalysisSpec) -> TransientSettings:
    value = spec.transient or {}
    stop_time = float(value.get("stop_time_s", 1e-3))
    time_step_mode = str(value.get("time_step_mode", "manual")).lower()
    requested_step = recommend_time_step_s(spec) if time_step_mode == "auto" else float(value.get("time_step_s", 1e-6))
    decimation = int(value.get("output_decimation", 10))
    decimation_mode = str(value.get("output_decimation_mode", "auto")).lower()
    playback_fps = int(value.get("playback_fps", 20))
    initial_condition = str(value.get("initial_condition", "operating_point"))
    max_internal_steps = max(1, int(value.get("max_internal_steps", 50000)))
    max_output_frames = max(2, int(value.get("max_output_frames", 1000)))
    max_solver_time_s = float(value.get("max_solver_time_s", 120.0))
    memory_budget_mb = float(value.get("memory_budget_mb", 2048.0))
    explicit_max_branches = value.get("max_branches")
    admitted_by_memory = max(16, int(sqrt(
        memory_budget_mb * 1024 * 1024 * TRANSIENT_WORKSPACE_FRACTION
        / DENSE_TRANSIENT_BYTES_PER_BRANCH_SQUARED
    )))
    max_branches = (
        admitted_by_memory
        if explicit_max_branches is None
        else min(max(16, int(explicit_max_branches)), admitted_by_memory)
    )
    capacitance_model = str(value.get("capacitance_model", "auto")).lower()
    visual_sample_limit = max(100, int(value.get("visual_sample_limit", 12000)))
    if stop_time <= 0 or requested_step <= 0 or requested_step > stop_time:
        raise ValueError("stop_time_s and time_step_s must be positive, with time_step_s no larger than stop_time_s")
    if time_step_mode not in {"auto", "manual"}:
        raise ValueError("time_step_mode must be auto or manual")
    if decimation < 1:
        raise ValueError("output_decimation must be a positive integer")
    if decimation_mode not in {"auto", "manual"}:
        raise ValueError("output_decimation_mode must be auto or manual")
    if not 1 <= playback_fps <= 30:
        raise ValueError("playback_fps must be between 1 and 30")
    if initial_condition not in {"zero", "operating_point"}:
        raise ValueError("initial_condition must be zero or operating_point")
    if max_solver_time_s <= 0:
        raise ValueError("max_solver_time_s must be positive")
    if memory_budget_mb < 32:
        raise ValueError("memory_budget_mb must be at least 32 MB")
    if capacitance_model not in {"auto", "stackup_shunt", "none"}:
        raise ValueError("capacitance_model must be auto, stackup_shunt, or none")
    steps = int(ceil(stop_time / requested_step))
    if steps > max_internal_steps:
        raise ValueError(f"transient run requires {steps} internal steps; the configured limit is {max_internal_steps}")
    frames = int(ceil(steps / decimation)) + 1
    if frames > max_output_frames:
        if decimation_mode == "manual":
            raise ValueError(f"transient run would save {frames} frames; increase output_decimation or the {max_output_frames}-frame limit")
        decimation = max(decimation, int(ceil(steps / max(max_output_frames - 1, 1))))
    return TransientSettings(
        stop_time_s=stop_time,
        requested_time_step_s=requested_step,
        time_step_s=stop_time / steps,
        internal_steps=steps,
        requested_output_decimation=int(value.get("output_decimation", 10)),
        output_decimation=decimation,
        output_decimation_mode=decimation_mode,
        playback_fps=playback_fps,
        initial_condition=initial_condition,
        time_step_mode=time_step_mode,
        max_internal_steps=max_internal_steps,
        max_output_frames=max_output_frames,
        max_branches=max_branches,
        configured_max_branches=None if explicit_max_branches is None else max(16, int(explicit_max_branches)),
        memory_admitted_max_branches=admitted_by_memory,
        max_solver_time_s=max_solver_time_s,
        memory_budget_bytes=int(memory_budget_mb * 1024 * 1024),
        capacitance_model=capacitance_model,
        visual_sample_limit=visual_sample_limit,
    )


def _minimum_conservative_memory_bytes(branch_count: int) -> int:
    """Return the branch-only dense workspace budget used for admission.

    This intentionally mirrors the pre-mesh RAM cap.  It is a conservative
    lower bound for user-facing diagnostics, not a replacement for the later
    topology-aware memory admission.
    """

    return int(ceil(
        max(0, int(branch_count)) ** 2 * DENSE_TRANSIENT_BYTES_PER_BRANCH_SQUARED
        / TRANSIENT_WORKSPACE_FRACTION
    ))


def _branch_admission_metadata(settings: TransientSettings, actual_branches: int) -> Dict[str, int | None]:
    return {
        "actual_branch_count": int(actual_branches),
        "configured_max_branches": settings.configured_max_branches,
        "memory_admitted_max_branches": settings.memory_admitted_max_branches,
        "effective_max_branches": settings.max_branches,
        "memory_budget_bytes": settings.memory_budget_bytes,
        "minimum_conservative_memory_bytes": _minimum_conservative_memory_bytes(actual_branches),
    }


def _profile(terminal: Dict[str, Any]) -> Dict[str, Any]:
    value = terminal.get("profile", {})
    if isinstance(value, str):
        return {"kind": value}
    return value if isinstance(value, dict) else {"kind": "constant"}


def _pwl_points(value: Any) -> List[Tuple[float, float]]:
    points: List[Tuple[float, float]] = []
    if isinstance(value, str):
        for token in value.replace(";", ",").split(","):
            token = token.strip()
            if not token:
                continue
            if ":" not in token:
                raise ValueError("piecewise-linear points must use time:value pairs")
            time_value, sample_value = token.split(":", 1)
            points.append((float(time_value.strip()), float(sample_value.strip())))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                points.append((float(item.get("time_s", item.get("time", 0))), float(item.get("value", 0))))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                points.append((float(item[0]), float(item[1])))
    points.sort(key=lambda item: item[0])
    if len(points) < 2 or any(right[0] <= left[0] for left, right in zip(points, points[1:])):
        raise ValueError("piecewise-linear waveforms require at least two strictly increasing time:value points")
    return points


def waveform_value(terminal: Dict[str, Any], time_s: float) -> float:
    """Evaluate a source or load waveform in its native V or A units."""

    profile = _profile(terminal)
    kind = str(profile.get("kind", "constant")).lower()
    high = float(terminal.get("voltage_v", terminal.get("current_a", terminal.get("value", 0))))
    if kind == "constant":
        return high
    low = float(profile.get("initial_value", 0))
    delay = max(0.0, float(profile.get("delay_s", 0)))
    rise = max(0.0, float(profile.get("rise_time_s", 0)))
    if kind == "step":
        if time_s < delay:
            return low
        if rise > 0 and time_s < delay + rise:
            return low + (high - low) * (time_s - delay) / rise
        return high
    if kind == "pulse":
        width = max(0.0, float(profile.get("pulse_width_s", 0)))
        fall = max(0.0, float(profile.get("fall_time_s", 0)))
        period = float(profile.get("period_s", 0))
        if period <= 0 or period < rise + width + fall:
            raise ValueError("pulse period must be positive and contain rise, high-time, and fall intervals")
        if time_s < delay:
            return low
        phase = (time_s - delay) % period
        if rise > 0 and phase < rise:
            return low + (high - low) * phase / rise
        if phase < rise + width:
            return high
        if fall > 0 and phase < rise + width + fall:
            return high + (low - high) * (phase - rise - width) / fall
        return low
    if kind == "piecewise_linear":
        points = _pwl_points(profile.get("points", profile.get("data", [])))
        if time_s <= points[0][0]:
            return points[0][1]
        if time_s >= points[-1][0]:
            return points[-1][1]
        for left, right in zip(points, points[1:]):
            if left[0] <= time_s <= right[0]:
                ratio = (time_s - left[0]) / (right[0] - left[0])
                return left[1] + (right[1] - left[1]) * ratio
    raise ValueError(f"unsupported terminal waveform kind: {kind}")


def validate_transient_spec(spec: AnalysisSpec) -> List[ValidationIssue]:
    issues: List[ValidationIssue] = []
    try:
        settings = transient_settings(spec)
    except (TypeError, ValueError) as exc:
        return [ValidationIssue("TRANSIENT_TIME_CONTROL_INVALID", "error", str(exc))]

    dynamic = 0
    edge_times: List[float] = []
    positive_load_pairs = {
        str(item.get("pair_id", "")): item
        for item in spec.loads
        if item.get("terminal_role", "load_positive") != "load_return" and item.get("pair_id")
    }
    for terminal in [*spec.sources, *spec.loads]:
        if terminal.get("terminal_role") == "load_return" and str(terminal.get("pair_id", "")) in positive_load_pairs:
            continue
        profile = _profile(terminal)
        kind = str(profile.get("kind", "constant")).lower()
        if kind not in {"constant", "step", "pulse", "piecewise_linear"}:
            issues.append(ValidationIssue("TRANSIENT_WAVEFORM_UNSUPPORTED", "error", f"{terminal.get('name', terminal.get('id', 'terminal'))} uses unsupported waveform {kind}."))
            continue
        if kind == "constant":
            continue
        dynamic += 1
        try:
            waveform_value(terminal, 0.0)
            waveform_value(terminal, settings.stop_time_s)
            if kind in {"step", "pulse"}:
                rise = float(profile.get("rise_time_s", 0))
                fall = float(profile.get("fall_time_s", 0)) if kind == "pulse" else rise
                if rise == 0 or (kind == "pulse" and fall == 0):
                    issues.append(ValidationIssue(
                        "IDEAL_EDGE_TIMESTEP_LIMITED",
                        "warning",
                        f"{terminal.get('name', terminal.get('id', 'terminal'))} contains an ideal edge; peak L di/dt is limited by the integration timestep.",
                        suggestion="Assign a measured or specified non-zero rise and fall time.",
                        status="approximate",
                    ))
                edge_times.extend(value for value in (rise, fall) if value > 0)
        except (TypeError, ValueError) as exc:
            issues.append(ValidationIssue("TRANSIENT_WAVEFORM_INVALID", "error", f"{terminal.get('name', terminal.get('id', 'terminal'))}: {exc}."))
    if not dynamic:
        issues.append(ValidationIssue(
            "TRANSIENT_STATIC_BOUNDARIES",
            "warning",
            "All source and load profiles are constant; the transient run will reproduce an operating point.",
            suggestion="Assign a step, pulse, or piecewise-linear waveform to a source or current sink.",
            status="approximate",
        ))
    if edge_times and settings.time_step_s > min(edge_times) / 5:
        issues.append(ValidationIssue(
            "TRANSIENT_EDGE_UNDERSAMPLED",
            "warning",
            "The integration timestep provides fewer than five samples across the fastest configured edge.",
            suggestion="Reduce time_step_s to at most one fifth of the shortest rise or fall time.",
            status="approximate",
        ))
    return issues


def _terminal_net(terminal: Dict[str, Any], spec: AnalysisSpec) -> str:
    return str(terminal.get("net") or terminal.get("net_name") or (spec.net_names[0] if spec.net_names else ""))


def _component(mesh: HybridMesh, net: str, seed: int) -> Tuple[set[int], set[int]]:
    adjacency: Dict[int, List[Tuple[int, int]]] = {}
    for index, branch in enumerate(mesh.branches):
        if branch.net != net:
            continue
        adjacency.setdefault(branch.node_p, []).append((branch.node_n, index))
        adjacency.setdefault(branch.node_n, []).append((branch.node_p, index))
    nodes = {seed}
    branches: set[int] = set()
    pending = [seed]
    while pending:
        node = pending.pop()
        for neighbor, branch_index in adjacency.get(node, []):
            branches.add(branch_index)
            if neighbor not in nodes:
                nodes.add(neighbor)
                pending.append(neighbor)
    return nodes, branches


def _admit_visual_records(records: Iterable[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Choose transient output records without changing the PEEC solve graph.

    Records carry their physical index only for result materialization. The
    shared sampler uses their stable geometry ownership to preserve layers,
    via kinds, and source coverage independently of mesh-builder order.
    """

    return stratified_sample_records(records, max(0, int(limit)))


def _factor(matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    with warnings.catch_warnings():
        warnings.simplefilter("error", LinAlgWarning)
        return lu_factor(matrix, check_finite=False)


def _assess_passive_inductance(matrix: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
    assessed, metrics = assess_symmetric_positive_semidefinite(matrix)
    return assessed, {
        **metrics,
        "minimum_eigenvalue_h": metrics["minimum_eigenvalue"],
        "maximum_eigenvalue_h": metrics["maximum_eigenvalue"],
        "passivity_tolerance_h": metrics["passivity_tolerance"],
    }


def _state_issue(solution: np.ndarray, step: int, time_s: float) -> ValidationIssue | None:
    if not np.all(np.isfinite(solution)):
        return ValidationIssue(
            "TRANSIENT_NUMERICAL_DIVERGENCE",
            "error",
            f"The transient state became non-finite at step {step} ({time_s:.9g} s).",
            suggestion="Use a coarser passive mesh, reduce the timestep, or select a validated sparse transient solver.",
        )
    magnitude = float(np.max(np.abs(solution), initial=0.0))
    if magnitude > MAX_ABSOLUTE_STATE_MAGNITUDE:
        return ValidationIssue(
            "TRANSIENT_NUMERICAL_DIVERGENCE",
            "error",
            f"The transient state exceeded the {MAX_ABSOLUTE_STATE_MAGNITUDE:.0e} numerical safety bound at step {step} ({time_s:.9g} s).",
            suggestion="Inspect matrix passivity and terminal constraints before accepting this setup.",
        )
    return None


def _stackup_profile(design: DesignIR) -> Tuple[Dict[str, float], List[Tuple[float, float, float]]]:
    copper_centers: Dict[str, float] = {}
    dielectrics: List[Tuple[float, float, float]] = []
    z_top = 0.0
    for item in design.stackup:
        name = str(item.get("name", ""))
        thickness = max(float(item.get("thickness") or item.get("thickness_mm") or 0), 0.0)
        z_bottom = z_top - thickness
        if name.endswith(".Cu"):
            copper_centers[name] = (z_top + z_bottom) / 2.0
        else:
            epsilon_value = item.get("epsilon_r", item.get("epsilonR"))
            if thickness > 0 and epsilon_value is not None and float(epsilon_value) > 1:
                dielectrics.append((z_bottom, z_top, float(epsilon_value)))
        z_top = z_bottom
    return copper_centers, dielectrics


def _dielectric_between(
    z_a: float,
    z_b: float,
    dielectrics: List[Tuple[float, float, float]],
) -> Tuple[float, float] | None:
    """Return thickness-weighted epsilon and physical dielectric height.

    Copper centers include half of each conductor thickness.  A field model
    needs the dielectric distance between the facing conductor surfaces, not
    that center-to-center distance, so only dielectric intervals contribute to
    the returned height.
    """

    low, high = sorted((z_a, z_b))
    weighted = 0.0
    covered = 0.0
    for bottom, top, epsilon_r in dielectrics:
        overlap = max(0.0, min(high, top) - max(low, bottom))
        weighted += overlap * epsilon_r
        covered += overlap
    if covered <= 0:
        return None
    return weighted / covered, covered


def _extract_stackup_capacitance(
    design: DesignIR,
    spec: AnalysisSpec,
    settings: TransientSettings,
    physical_branches: List[Any],
    branch_endpoints: List[Tuple[int, int]],
    node_metadata: List[Dict[str, Any]],
    node_count: int,
) -> Tuple[np.ndarray, Dict[str, Any], np.ndarray]:
    matrix = np.zeros((node_count, node_count), dtype=float)
    branch_capacitance = np.zeros(len(physical_branches), dtype=float)
    if settings.capacitance_model == "none":
        return matrix, {"model": "none", "status": "unsupported", "total_capacitance_f": 0.0}, branch_capacitance

    copper_centers, dielectrics = _stackup_profile(design)
    if len(copper_centers) < 2 or not dielectrics:
        return matrix, {
            "model": "stackup_shunt", "status": "unsupported", "total_capacitance_f": 0.0,
            "reason": "Stackup needs at least two copper layers and dielectric epsilon/thickness data.",
        }, branch_capacitance

    return_mode = str(spec.return_path.get("mode", "implicit"))
    return_net = str(spec.return_path.get("net", "")) if return_mode in {"explicit", "isolated_secondary"} else ""
    physical_metadata = node_metadata[:max((max(pair) for pair in branch_endpoints[:len(physical_branches)]), default=-1) + 1]
    reference_nodes = [
        index for index, item in enumerate(physical_metadata)
        if return_net and str(item.get("net", "")) == return_net and str(item.get("layer", "")) in copper_centers
    ]
    extracted = 0
    skipped_vias = 0
    skipped_reference = 0
    reference_layers: set[str] = set()

    def stamp(node: int, reference: int | None, value: float) -> None:
        if value <= 0:
            return
        matrix[node, node] += value
        if reference is not None and reference != node:
            matrix[reference, reference] += value
            matrix[node, reference] -= value
            matrix[reference, node] -= value

    for index, branch in enumerate(physical_branches):
        if branch.kind == "via" or "via" in branch.kind:
            skipped_vias += 1
            continue
        layer = str(branch.layer)
        layer_z = copper_centers.get(layer)
        if layer_z is None or branch.length_mm <= 0:
            skipped_reference += 1
            continue
        reference_node: int | None = None
        reference_layer = ""
        if return_net:
            candidates = [node for node in reference_nodes if str(node_metadata[node].get("layer", "")) != layer]
            if candidates:
                midpoint_x = (branch.start_mm[0] + branch.end_mm[0]) / 2.0
                midpoint_y = (branch.start_mm[1] + branch.end_mm[1]) / 2.0
                reference_node = min(candidates, key=lambda node: (
                    abs(copper_centers[str(node_metadata[node]["layer"])] - layer_z),
                    (float(node_metadata[node]["x_mm"]) - midpoint_x) ** 2 + (float(node_metadata[node]["y_mm"]) - midpoint_y) ** 2,
                ))
                reference_layer = str(node_metadata[reference_node]["layer"])
        else:
            alternatives = [(name, z) for name, z in copper_centers.items() if name != layer]
            if alternatives:
                reference_layer = min(alternatives, key=lambda item: abs(item[1] - layer_z))[0]
        if not reference_layer:
            skipped_reference += 1
            continue
        reference_z = copper_centers[reference_layer]
        dielectric = _dielectric_between(layer_z, reference_z, dielectrics)
        if dielectric is None:
            skipped_reference += 1
            continue
        epsilon_r, height_mm = dielectric
        capacitance = estimate_line_capacitance_per_m(branch.width_mm, height_mm, epsilon_r) * branch.length_mm * 1e-3
        if branch.kind.startswith("zone") or branch.kind.startswith("pad"):
            capacitance *= 0.5
        if not np.isfinite(capacitance) or capacitance <= 0:
            continue
        branch_capacitance[index] = capacitance
        node_p, node_n = branch_endpoints[index]
        stamp(node_p, reference_node, capacitance / 2.0)
        stamp(node_n, reference_node, capacitance / 2.0)
        extracted += 1
        reference_layers.add(reference_layer)

    total = float(np.sum(branch_capacitance))
    return matrix, {
        "contract": "spike/distributed-capacitance/v1",
        "model": "hammerstad_jensen_single_reference",
        "status": "approximate" if extracted else "unsupported",
        "reference_mode": "explicit_return_conductor" if return_net else "implicit_nearest_copper",
        "reference_net": return_net,
        "reference_layers": sorted(reference_layers),
        "estimated_branch_count": extracted,
        "skipped_via_branch_count": skipped_vias,
        "skipped_reference_branch_count": skipped_reference,
        "total_capacitance_f": total,
    }, branch_capacitance


def _apply_memory_budget(
    settings: TransientSettings,
    node_count: int,
    branch_count: int,
    physical_count: int,
    matrix_order: int,
    via_count: int,
) -> Tuple[TransientSettings, Dict[str, int], ValidationIssue | None]:
    values_per_frame = 2 * node_count + 5 * physical_count + via_count
    resident_frame_bytes = max(values_per_frame * 32 + 2048, 4096)
    compact_numeric_bytes = values_per_frame * 8
    static_layout_bytes = (node_count + physical_count + via_count) * 320
    dense_workspace_bytes = int(8 * (
        6 * physical_count * physical_count
        + 4 * branch_count * branch_count
        + 3 * matrix_order * matrix_order
        + node_count * node_count
    ))
    fixed_bytes = dense_workspace_bytes + static_layout_bytes
    requested_frames = int(ceil(settings.internal_steps / settings.output_decimation)) + 1
    allowed_by_memory = max(0, (settings.memory_budget_bytes - fixed_bytes) // resident_frame_bytes)
    allowed_frames = min(settings.max_output_frames, int(allowed_by_memory))
    issue: ValidationIssue | None = None
    effective = settings
    if allowed_frames < 2:
        estimate = {
            "estimated_dense_workspace_bytes": dense_workspace_bytes,
            "estimated_static_layout_bytes": static_layout_bytes,
            "estimated_resident_frame_bytes": resident_frame_bytes,
            "compact_numeric_bytes_per_frame": compact_numeric_bytes,
            "estimated_output_bytes": requested_frames * resident_frame_bytes + static_layout_bytes,
            "estimated_peak_worker_bytes": fixed_bytes + requested_frames * resident_frame_bytes,
            "effective_frame_count": requested_frames,
        }
        return effective, estimate, ValidationIssue(
            "TRANSIENT_MEMORY_BUDGET_EXCEEDED", "error",
            f"The {settings.memory_budget_bytes / (1024 * 1024):.0f} MB budget cannot hold the dense solver workspace and two output frames.",
            suggestion="Coarsen or isolate the conductor mesh, increase the memory budget, or install a sparse transient solver.",
        )
    if requested_frames > allowed_frames:
        if settings.output_decimation_mode == "manual":
            estimate = {
                "estimated_dense_workspace_bytes": dense_workspace_bytes,
                "estimated_static_layout_bytes": static_layout_bytes,
                "estimated_resident_frame_bytes": resident_frame_bytes,
                "compact_numeric_bytes_per_frame": compact_numeric_bytes,
                "estimated_output_bytes": requested_frames * resident_frame_bytes + static_layout_bytes,
                "estimated_peak_worker_bytes": fixed_bytes + requested_frames * resident_frame_bytes,
                "effective_frame_count": requested_frames,
            }
            return effective, estimate, ValidationIssue(
                "TRANSIENT_MEMORY_BUDGET_EXCEEDED", "error",
                f"The requested {requested_frames} frames exceed the configured transient memory budget.",
                suggestion="Enable automatic output decimation, save fewer frames, or increase memory_budget_mb.",
            )
        decimation = max(settings.output_decimation, int(ceil(settings.internal_steps / max(allowed_frames - 1, 1))))
        effective = replace(settings, output_decimation=decimation)
        issue = ValidationIssue(
            "TRANSIENT_OUTPUT_AUTO_DECIMATED", "warning",
            f"Output decimation increased from {settings.output_decimation} to {decimation} to respect the memory and frame limits.",
            status="approximate",
        )
    frames = int(ceil(effective.internal_steps / effective.output_decimation)) + 1
    estimate = {
        "estimated_dense_workspace_bytes": dense_workspace_bytes,
        "estimated_static_layout_bytes": static_layout_bytes,
        "estimated_resident_frame_bytes": resident_frame_bytes,
        "compact_numeric_bytes_per_frame": compact_numeric_bytes,
        "estimated_output_bytes": frames * resident_frame_bytes + static_layout_bytes,
        "estimated_peak_worker_bytes": fixed_bytes + frames * resident_frame_bytes,
        "effective_frame_count": frames,
    }
    return effective, estimate, issue


def _failed(
    spec: AnalysisSpec,
    issues: Iterable[ValidationIssue],
    model_status: str = "failed",
    summary: Dict[str, Any] | None = None,
    provenance: Dict[str, Any] | None = None,
) -> AnalysisResult:
    return AnalysisResult(
        analysis_id=spec.analysis_id or "peec-rl-transient",
        mode=spec.mode,
        status="failed",
        model_status=model_status,
        summary=summary or {},
        issues=list(issues),
        provenance={"solver": "spike-peec-rl-transient/v0.1", "solved": False, **(provenance or {})},
    )


def solve_peec_rl_transient(design: DesignIR, spec: AnalysisSpec) -> AnalysisResult:
    solve_started = perf_counter()
    if spec.mode != "transient":
        return _failed(spec, [ValidationIssue("PEEC_TRANSIENT_MODE_UNSUPPORTED", "error", "The PEEC RL transient plugin only accepts transient analyses.")], "unsupported")
    if not native_available():
        return _failed(spec, [ValidationIssue("PEEC_NATIVE_MISSING", "error", "The native PEEC runtime is not installed.")], "unsupported")
    settings_issues = validate_transient_spec(spec)
    if any(issue.severity == "error" for issue in settings_issues):
        return _failed(spec, settings_issues)
    settings = transient_settings(spec)

    mesh = build_hybrid_mesh(design, spec)
    issues = [*mesh.issues, *settings_issues]
    if mesh.truncated or not mesh.branches:
        return _failed(spec, issues + ([] if mesh.branches else [ValidationIssue("NO_PEEC_FILAMENTS", "error", "No conductor branches matched the transient net selection.")]))

    source_locations: List[Tuple[Dict[str, Any], int, str]] = []
    load_locations: List[Tuple[Dict[str, Any], int, str]] = []
    for terminal, collection, code in [
        *[(item, source_locations, "SOURCE") for item in spec.sources],
        *[(item, load_locations, "LOAD") for item in spec.loads],
    ]:
        net = _terminal_net(terminal, spec)
        node = nearest_mesh_node(mesh, terminal, net)
        if node is None:
            issues.append(ValidationIssue(f"{code}_NOT_ON_TRANSIENT_MESH", "error", f"{terminal.get('name', terminal.get('id', code.lower()))} cannot snap to the connected PEEC mesh on {net}."))
        else:
            collection.append((terminal, int(node), net))
    if any(issue.severity == "error" for issue in issues):
        return _failed(spec, issues)

    active_nodes: set[int] = set()
    active_branches: set[int] = set()
    for _, node, net in source_locations:
        component_nodes, component_branches = _component(mesh, net, node)
        active_nodes.update(component_nodes)
        active_branches.update(component_branches)
    for terminal, node, net in load_locations:
        if node not in active_nodes:
            issues.append(ValidationIssue("TRANSIENT_LOAD_DISCONNECTED", "error", f"{terminal.get('name', terminal.get('id', 'load'))} is not connected to a source on {net}."))
    if not active_branches:
        issues.append(ValidationIssue("TRANSIENT_NO_SOURCE_COMPONENT", "error", "No source-connected conductor component contains a solvable branch."))
    if any(issue.severity == "error" for issue in issues):
        return _failed(spec, issues)

    physical_indices = sorted(active_branches)
    if len(physical_indices) > settings.max_branches:
        admission = _branch_admission_metadata(settings, len(physical_indices))
        configured_cap = (
            f"The request explicitly caps this run at {settings.configured_max_branches} branches; "
            if settings.configured_max_branches is not None else ""
        )
        minimum_mb = ceil(admission["minimum_conservative_memory_bytes"] / (1024 * 1024))
        return _failed(spec, issues + [ValidationIssue(
            "TRANSIENT_DENSE_BRANCH_LIMIT",
            "error",
            f"The selected source-connected mesh has {len(physical_indices)} branches; the effective dense PEEC transient limit is {settings.max_branches}. {configured_cap}"
            f"The {settings.memory_budget_bytes / (1024 * 1024):.0f} MB memory budget independently admits at most {settings.memory_admitted_max_branches} branches.",
            suggestion=(
                f"Coarsen or isolate the mesh. To admit {len(physical_indices)} branches under the conservative dense-workspace rule, "
                f"configure at least {minimum_mb:.0f} MB and set max_branches to at least {len(physical_indices)}; "
                "otherwise use a sparse/distributed transient solver plugin."
            ),
        )], summary={"branch_admission": admission}, provenance={"branch_admission": admission})
    physical_branches = [mesh.branches[index] for index in physical_indices]
    physical_node_ids = sorted({node for branch in physical_branches for node in (branch.node_p, branch.node_n)})
    physical_node_set = set(physical_node_ids)
    node_index = {node_id: index for index, node_id in enumerate(physical_node_ids)}
    node_metadata: List[Dict[str, Any]] = [
        {
            "global_id": node_id,
            "x_mm": mesh.nodes[node_id].x_mm,
            "y_mm": mesh.nodes[node_id].y_mm,
            "z_mm": mesh.nodes[node_id].z_mm,
            "layer": mesh.nodes[node_id].layer,
            "net": mesh.nodes[node_id].net,
            "physical": True,
        }
        for node_id in physical_node_ids
    ]
    branch_endpoints: List[Tuple[int, int]] = [
        (node_index[branch.node_p], node_index[branch.node_n]) for branch in physical_branches
    ]
    contact_resistances: List[float] = []
    known_sources: Dict[int, Dict[str, Any]] = {}
    attached_loads: List[Tuple[int, Dict[str, Any]]] = []

    def add_external_node(terminal: Dict[str, Any], copper_node: int) -> int:
        metadata = node_metadata[copper_node]
        node_metadata.append({
            **metadata,
            "global_id": None,
            "physical": False,
            "terminal_id": str(terminal.get("id", "")),
        })
        return len(node_metadata) - 1

    for terminal, global_node, _ in source_locations:
        if global_node not in physical_node_set:
            continue
        copper_node = node_index[global_node]
        resistance = max(0.0, float(terminal.get("contact_resistance_ohm", 0))) + max(0.0, float(terminal.get("package_resistance_ohm", 0)))
        source_node = copper_node
        if resistance > 0:
            source_node = add_external_node(terminal, copper_node)
            branch_endpoints.append((source_node, copper_node))
            contact_resistances.append(resistance)
        previous = known_sources.get(source_node)
        if previous is not None:
            samples = (0.0, settings.stop_time_s / 2, settings.stop_time_s)
            if any(abs(waveform_value(previous, time_s) - waveform_value(terminal, time_s)) > 1e-9 for time_s in samples):
                issues.append(ValidationIssue("CONFLICTING_TRANSIENT_SOURCES", "error", "Two ideal voltage sources assign different waveforms to the same PEEC node."))
        known_sources[source_node] = terminal

    for terminal, global_node, _ in load_locations:
        if global_node not in physical_node_set:
            continue
        copper_node = node_index[global_node]
        resistance = max(0.0, float(terminal.get("contact_resistance_ohm", 0))) + max(0.0, float(terminal.get("package_resistance_ohm", 0)))
        load_node = copper_node
        if resistance > 0:
            load_node = add_external_node(terminal, copper_node)
            branch_endpoints.append((copper_node, load_node))
            contact_resistances.append(resistance)
        attached_loads.append((load_node, terminal))
    if any(issue.severity == "error" for issue in issues):
        return _failed(spec, issues)

    physical_count = len(physical_branches)
    branch_count = len(branch_endpoints)
    node_count = len(node_metadata)
    known_nodes = sorted(known_sources)
    unknown_nodes = [index for index in range(node_count) if index not in known_sources]
    unknown_position = {node: index for index, node in enumerate(unknown_nodes)}
    settings, resource_estimate, budget_issue = _apply_memory_budget(
        settings,
        len(physical_node_ids),
        branch_count,
        physical_count,
        branch_count + len(unknown_nodes),
        sum(branch.kind == "via" or "via" in branch.kind for branch in physical_branches),
    )
    if budget_issue is not None:
        issues.append(budget_issue)
        if budget_issue.severity == "error":
            return _failed(spec, issues)
    capacitance, capacitance_info, branch_capacitance = _extract_stackup_capacitance(
        design, spec, settings, physical_branches, branch_endpoints, node_metadata, node_count,
    )

    try:
        active_mesh = HybridMesh(nodes=mesh.nodes, branches=physical_branches, target_size_mm=mesh.target_size_mm)
        solver, native_config = _make_native_solver(active_mesh, _dielectric_epsilon(design))
        physical_inductance = _dense(solver.compute_partial_inductance())
        physical_inductance, passivity = _assess_passive_inductance(physical_inductance)
        physical_resistance = _dense(solver.compute_resistance(0.0))
    except Exception as exc:
        return _failed(spec, issues + [ValidationIssue("PEEC_MATRIX_EXTRACTION_FAILED", "error", f"Native PEEC matrix extraction failed: {exc}.")])
    if perf_counter() - solve_started > settings.max_solver_time_s:
        return _failed(spec, issues + [ValidationIssue(
            "TRANSIENT_SOLVER_TIME_LIMIT", "error",
            f"Matrix extraction exceeded the configured {settings.max_solver_time_s:.3g} s solver limit.",
            suggestion="Coarsen or isolate the mesh, increase max_solver_time_s, or use a sparse solver plugin.",
        )])

    correction_ratio = float(passivity["frobenius_correction_ratio"])
    if int(passivity["negative_eigenmode_count"]) > 0:
        return _failed(spec, issues + [ValidationIssue(
            "TRANSIENT_INDUCTANCE_NONPASSIVE",
            "error",
            f"The physical partial-inductance matrix contains {passivity['negative_eigenmode_count']} negative-energy mode(s); no passivity projection was applied.",
            suggestion="Refine overlapping physical copper primitives or use a validated volume-integral PEEC extractor.",
        )], provenance={
            "numerical_quality": {"inductance_passivity": passivity},
            "failure_stage": "physical_inductance_admission",
            "inductance_units": "H",
        })

    inductance = np.zeros((branch_count, branch_count), dtype=float)
    resistance = np.zeros((branch_count, branch_count), dtype=float)
    inductance[:physical_count, :physical_count] = physical_inductance
    resistance[:physical_count, :physical_count] = physical_resistance
    for offset, value in enumerate(contact_resistances):
        resistance[physical_count + offset, physical_count + offset] = value
    characteristic_times = [
        sqrt(float(physical_inductance[index, index]) * float(branch_capacitance[index]))
        for index in range(physical_count)
        if physical_inductance[index, index] > 0 and branch_capacitance[index] > 0
    ]
    fastest_lc_time_s = min(characteristic_times, default=0.0)
    incidence = np.zeros((node_count, branch_count), dtype=float)
    for column, (node_p, node_n) in enumerate(branch_endpoints):
        incidence[node_p, column] = 1.0
        incidence[node_n, column] = -1.0

    known_incidence = incidence[known_nodes, :] if known_nodes else np.zeros((0, branch_count))
    unknown_incidence = incidence[unknown_nodes, :] if unknown_nodes else np.zeros((0, branch_count))
    unknown_capacitance = capacitance[np.ix_(unknown_nodes, unknown_nodes)] if unknown_nodes else np.zeros((0, 0))
    known_capacitance = capacitance[np.ix_(unknown_nodes, known_nodes)] if unknown_nodes and known_nodes else np.zeros((len(unknown_nodes), len(known_nodes)))

    def source_values(time_s: float) -> np.ndarray:
        return np.asarray([waveform_value(known_sources[node], time_s) for node in known_nodes], dtype=float)

    positive_pairs = {
        str(terminal.get("pair_id", "")): terminal
        for _, terminal in attached_loads
        if terminal.get("terminal_role", "load_positive") != "load_return" and terminal.get("pair_id")
    }

    def load_current(terminal: Dict[str, Any], time_s: float) -> float:
        if terminal.get("terminal_role") == "load_return":
            positive = positive_pairs.get(str(terminal.get("pair_id", "")))
            if positive is not None:
                return -abs(waveform_value(positive, time_s))
        return waveform_value(terminal, time_s)

    def injections(time_s: float) -> np.ndarray:
        result = np.zeros(len(unknown_nodes), dtype=float)
        for node, terminal in attached_loads:
            position = unknown_position.get(node)
            if position is not None:
                result[position] -= load_current(terminal, time_s)
        return result

    def kkt(branch_matrix: np.ndarray, nodal_matrix: np.ndarray | None = None) -> np.ndarray:
        matrix = np.zeros((branch_count + len(unknown_nodes), branch_count + len(unknown_nodes)), dtype=float)
        matrix[:branch_count, :branch_count] = branch_matrix
        if unknown_nodes:
            matrix[:branch_count, branch_count:] = -unknown_incidence.T
            matrix[branch_count:, :branch_count] = unknown_incidence
            if nodal_matrix is not None:
                matrix[branch_count:, branch_count:] = nodal_matrix
        return matrix

    dynamic_matrix = kkt(
        resistance + inductance / settings.time_step_s,
        unknown_capacitance / settings.time_step_s,
    )
    try:
        dynamic_factor = _factor(dynamic_matrix)
    except (ValueError, LinAlgWarning) as exc:
        return _failed(spec, issues + [ValidationIssue("TRANSIENT_MNA_SINGULAR", "error", f"The PEEC transient matrix is singular: {exc}.")])

    currents = np.zeros(branch_count, dtype=float)
    voltages = np.zeros(node_count, dtype=float)
    source_by_net = {
        _terminal_net(terminal, spec): waveform_value(terminal, 0.0)
        for terminal, _, _ in source_locations
    }
    for index, metadata in enumerate(node_metadata):
        voltages[index] = source_by_net.get(str(metadata.get("net", "")), 0.0)
    for node, value in zip(known_nodes, source_values(0.0)):
        voltages[node] = value
    if settings.initial_condition == "operating_point":
        try:
            dc_factor = _factor(kkt(resistance))
            rhs = np.zeros(branch_count + len(unknown_nodes), dtype=float)
            rhs[:branch_count] = known_incidence.T @ source_values(0.0)
            rhs[branch_count:] = injections(0.0)
            solution = lu_solve(dc_factor, rhs, check_finite=False)
            state_issue = _state_issue(solution, 0, 0.0)
            if state_issue is not None:
                return _failed(spec, issues + [state_issue])
            currents = solution[:branch_count]
            for node, value in zip(unknown_nodes, solution[branch_count:]):
                voltages[node] = value
        except (ValueError, LinAlgWarning) as exc:
            return _failed(spec, issues + [ValidationIssue("TRANSIENT_OPERATING_POINT_FAILED", "error", f"The t=0 operating point is singular: {exc}.")])

    physical_areas = np.asarray([max(branch.width_mm * branch.thickness_mm, 1e-15) for branch in physical_branches])
    physical_resistance_diagonal = np.diag(resistance)[:physical_count]
    adjacency: Dict[int, List[int]] = {}
    for branch_index, (node_p, node_n) in enumerate(branch_endpoints[:physical_count]):
        adjacency.setdefault(node_p, []).append(branch_index)
        adjacency.setdefault(node_n, []).append(branch_index)
    probe_nodes: List[Tuple[Dict[str, Any], int, int]] = []
    for probe in spec.probes:
        global_node = nearest_mesh_node(mesh, probe, str(probe.get("net", "")))
        if global_node in node_index:
            probe_nodes.append((probe, node_index[int(global_node)], int(global_node)))
    probe_history: Dict[str, Dict[str, Any]] = {
        str(probe.get("id", probe.get("name", f"probe-{index + 1}"))): {
            "id": str(probe.get("id", probe.get("name", f"probe-{index + 1}"))),
            "name": str(probe.get("name", probe.get("id", f"Probe {index + 1}"))),
            "net": str(probe.get("net", node_metadata[node].get("net", ""))),
            "requested_layer": probe.get("layer"),
            "layer": str(node_metadata[node].get("layer", probe.get("layer", ""))),
            "resolved_layer": str(node_metadata[node].get("layer", probe.get("layer", ""))),
            "connected_layers": sorted({
                candidate.layer
                for candidate in mesh.nodes
                if candidate.net == mesh.nodes[global_node].net
                and abs(candidate.x_mm - mesh.nodes[global_node].x_mm) <= 1e-6
                and abs(candidate.y_mm - mesh.nodes[global_node].y_mm) <= 1e-6
            }),
            "position_mm": probe.get("position_mm", [node_metadata[node]["x_mm"], node_metadata[node]["y_mm"]]),
            "times_s": [],
            "voltage_v": [],
            "voltage_drop_v": [],
            "current_a": [],
            "current_density_a_mm2": [],
        }
        for index, (probe, node, global_node) in enumerate(probe_nodes)
    }

    def net_references(time_s: float) -> Dict[str, float]:
        result: Dict[str, float] = {}
        for terminal, _, net in source_locations:
            result[net] = max(result.get(net, float("-inf")), waveform_value(terminal, time_s))
        return result

    node_records = [
        {
            "id": f"node-{metadata['global_id']}",
            "source_id": f"node-{metadata['global_id']}",
            "source_kind": "node",
            "net": metadata["net"],
            "layer": metadata["layer"],
            "x_mm": metadata["x_mm"],
            "y_mm": metadata["y_mm"],
            "_physical_index": index,
        }
        for index, metadata in enumerate(node_metadata[:len(physical_node_ids)])
    ]
    node_output_records = _admit_visual_records(
        node_records,
        max(50, settings.visual_sample_limit // 3),
    )
    node_output_indexes = [int(record["_physical_index"]) for record in node_output_records]
    from .hybrid_mesh import is_visualizable_physical_branch
    branch_records = [
        {
            "id": branch.id,
            "source_id": branch.source_id,
            "source_kind": branch.kind,
            "net": branch.net,
            "layer": branch.layer,
            "start_mm": branch.start_mm,
            "end_mm": branch.end_mm,
            "_physical_index": index,
        }
        for index, branch in enumerate(physical_branches)
        if is_visualizable_physical_branch(branch)
    ]
    branch_output_records = _admit_visual_records(
        branch_records,
        max(50, settings.visual_sample_limit - len(node_output_indexes)),
    )
    branch_output_indexes = [int(record["_physical_index"]) for record in branch_output_records]
    node_layout = [
        {
            "x_mm": metadata["x_mm"], "y_mm": metadata["y_mm"], "z_mm": metadata["z_mm"],
            "layer": metadata["layer"], "net": metadata["net"], "element_id": f"node-{metadata['global_id']}",
        }
        for index in node_output_indexes
        for metadata in [node_metadata[index]]
    ]
    branch_layout = [
        {
            "x_mm": (branch.start_mm[0] + branch.end_mm[0]) / 2,
            "y_mm": (branch.start_mm[1] + branch.end_mm[1]) / 2,
            "z_mm": (branch.start_mm[2] + branch.end_mm[2]) / 2,
            "layer": branch.layer, "net": branch.net, "element_id": branch.id,
            "width_mm": branch.width_mm, "kind": branch.kind,
        }
        for index in branch_output_indexes
        for branch in [physical_branches[index]]
    ]
    via_indexes = [index for index in branch_output_indexes if physical_branches[index].kind == "via" or "via" in physical_branches[index].kind]
    branch_output_position = {branch_index: output_index for output_index, branch_index in enumerate(branch_output_indexes)}
    via_layout = [branch_layout[branch_output_position[index]] for index in via_indexes]
    branch_directions = []
    for branch_index in branch_output_indexes:
        branch = physical_branches[branch_index]
        length = max(branch.length_mm, 1e-15)
        branch_directions.append([
            (branch.end_mm[0] - branch.start_mm[0]) / length,
            (branch.end_mm[1] - branch.start_mm[1]) / length,
            (branch.end_mm[2] - branch.start_mm[2]) / length,
        ])
    series_layouts = {"nodes": node_layout, "branches": branch_layout, "vias": via_layout}
    field_layouts = {
        "voltage_v": "nodes", "voltage_drop_v": "nodes", "current_a": "branches",
        "current_density_a_mm2": "branches", "power_loss_w": "branches",
        "via_current_density_a_mm2": "vias",
    }

    def compact_frame(time_s: float, state_currents: np.ndarray, state_voltages: np.ndarray) -> Dict[str, Any]:
        references = net_references(time_s)
        voltage_values = [float(state_voltages[index]) for index in node_output_indexes]
        drop_values = [
            float(references.get(str(node_metadata[index]["net"]), 0.0) - state_voltages[index])
            for index in node_output_indexes
        ]
        signed_density = [float(state_currents[index]) / physical_areas[index] for index in branch_output_indexes]
        current_values = [abs(float(state_currents[index])) for index in branch_output_indexes]
        density_values = [abs(value) for value in signed_density]
        loss_values = [
            float(state_currents[index] * state_currents[index] * physical_resistance_diagonal[index])
            for index in branch_output_indexes
        ]
        via_values = [abs(float(state_currents[index])) / physical_areas[index] for index in via_indexes]
        for probe, node, _global_node in probe_nodes:
            probe_id = str(probe.get("id", probe.get("name", "probe")))
            history = probe_history[probe_id]
            adjacent = adjacency.get(node, [])
            history["times_s"].append(float(time_s))
            history["voltage_v"].append(float(state_voltages[node]))
            history["voltage_drop_v"].append(float(references.get(str(node_metadata[node]["net"]), 0.0) - state_voltages[node]))
            history["current_a"].append(max((abs(float(state_currents[index])) for index in adjacent), default=0.0))
            history["current_density_a_mm2"].append(max((abs(float(state_currents[index])) / physical_areas[index] for index in adjacent), default=0.0))
        return {
            "time_s": float(time_s),
            "scalar_values": {
                "voltage_v": voltage_values,
                "voltage_drop_v": drop_values,
                "current_a": current_values,
                "current_density_a_mm2": density_values,
                "power_loss_w": loss_values,
                "via_current_density_a_mm2": via_values,
            },
            "vector_values": {"current_density": signed_density},
        }

    def materialize_frame(value: Dict[str, Any]) -> Dict[str, Any]:
        scalar_fields = {
            field: [{**sample, "value": float(samples[index])} for index, sample in enumerate(series_layouts[layout])]
            for field, samples in value["scalar_values"].items()
            for layout in [field_layouts[field]]
        }
        signed = value["vector_values"]["current_density"]
        vectors = [{
            **sample,
            "value": abs(float(signed[index])),
            "magnitude": abs(float(signed[index])),
            "vector": [float(signed[index]) * direction[0], float(signed[index]) * direction[1], float(signed[index]) * direction[2]],
        } for index, (sample, direction) in enumerate(zip(branch_layout, branch_directions))]
        return {"time_s": value["time_s"], "scalar_fields": scalar_fields, "vector_fields": {"current_density": vectors}}

    times: List[float] = [0.0]
    frames: List[Dict[str, Any]] = [compact_frame(0.0, currents, voltages)]
    first_values = frames[0]["scalar_values"]
    max_drop = max(first_values["voltage_drop_v"], default=0.0)
    max_overshoot = max((-value for value in first_values["voltage_drop_v"]), default=0.0)
    max_density = max(first_values["current_density_a_mm2"], default=0.0)
    max_current = max(first_values["current_a"], default=0.0)
    max_loss = sum(first_values["power_loss_w"])
    peak_inductive_drop = 0.0
    peak_capacitive_current = 0.0
    max_scaled_residual = 0.0
    dynamic_norm = float(np.linalg.norm(dynamic_matrix, ord=np.inf))

    for step in range(1, settings.internal_steps + 1):
        time_s = step * settings.time_step_s
        previous_currents = currents
        previous_voltages = voltages.copy()
        current_source_values = source_values(time_s)
        rhs = np.zeros(branch_count + len(unknown_nodes), dtype=float)
        rhs[:branch_count] = inductance @ previous_currents / settings.time_step_s + known_incidence.T @ current_source_values
        if unknown_nodes:
            previous_unknown = previous_voltages[unknown_nodes]
            previous_known = previous_voltages[known_nodes] if known_nodes else np.zeros(0)
            rhs[branch_count:] = (
                injections(time_s)
                + unknown_capacitance @ previous_unknown / settings.time_step_s
                + known_capacitance @ (previous_known - current_source_values) / settings.time_step_s
            )
        solution = lu_solve(dynamic_factor, rhs, check_finite=False)
        state_issue = _state_issue(solution, step, time_s)
        if state_issue is not None:
            return _failed(spec, issues + [state_issue])
        currents = solution[:branch_count]
        for node, value in zip(known_nodes, current_source_values):
            voltages[node] = value
        for node, value in zip(unknown_nodes, solution[branch_count:]):
            voltages[node] = value
        inductive_drop = inductance @ (currents - previous_currents) / settings.time_step_s
        peak_inductive_drop = max(peak_inductive_drop, float(np.max(np.abs(inductive_drop), initial=0.0)))
        capacitive_current = capacitance @ (voltages - previous_voltages) / settings.time_step_s
        peak_capacitive_current = max(peak_capacitive_current, float(np.max(np.abs(capacitive_current), initial=0.0)))
        references = net_references(time_s)
        physical_voltages = voltages[:len(physical_node_ids)]
        drops = np.asarray([
            references.get(str(node_metadata[index]["net"]), 0.0) - physical_voltages[index]
            for index in range(len(physical_node_ids))
        ])
        densities = np.abs(currents[:physical_count]) / physical_areas
        max_drop = max(max_drop, float(np.max(drops, initial=0.0)))
        max_overshoot = max(max_overshoot, float(np.max(-drops, initial=0.0)))
        max_density = max(max_density, float(np.max(densities, initial=0.0)))
        max_current = max(max_current, float(np.max(np.abs(currents[:physical_count]), initial=0.0)))
        max_loss = max(max_loss, float(np.sum(currents[:physical_count] ** 2 * physical_resistance_diagonal)))
        if step % 16 == 0 and perf_counter() - solve_started > settings.max_solver_time_s:
            return _failed(spec, issues + [ValidationIssue(
                "TRANSIENT_SOLVER_TIME_LIMIT", "error",
                f"Transient integration reached the configured {settings.max_solver_time_s:.3g} s wall-time limit at step {step} of {settings.internal_steps}.",
                suggestion="Shorten the run, coarsen the mesh, increase the wall-time limit, or use a sparse solver plugin.",
            )])
        if step % settings.output_decimation == 0 or step == settings.internal_steps:
            residual = dynamic_matrix @ solution - rhs
            residual_scale = max(
                float(np.linalg.norm(rhs, ord=np.inf))
                + dynamic_norm * float(np.linalg.norm(solution, ord=np.inf)),
                1e-30,
            )
            scaled_residual = float(np.linalg.norm(residual, ord=np.inf) / residual_scale)
            if not np.isfinite(scaled_residual) or scaled_residual > 1e-7:
                return _failed(spec, issues + [ValidationIssue(
                    "TRANSIENT_LINEAR_RESIDUAL_FAILED",
                    "error",
                    f"The scaled linear residual is {scaled_residual:.3g} at step {step}; the transient state is not numerically trustworthy.",
                    suggestion="Refine matrix conditioning or use a validated sparse transient solver.",
                )])
            max_scaled_residual = max(max_scaled_residual, scaled_residual)
            times.append(float(time_s))
            frames.append(compact_frame(time_s, currents, voltages))

    source_ids = {branch.source_id for branch in physical_branches}
    preview_candidates = [
        cell for cell in mesh.cells
        if str(cell.get("source_id", "")) in source_ids
    ]
    preview_cells = _admit_visual_records(
        preview_candidates,
        max(int(spec.mesh.get("max_preview_cells", 25000)), 100),
    )
    final_frame = materialize_frame(frames[-1])
    probes = []
    for history in probe_history.values():
        probes.append({
            "id": history["id"], "name": history["name"], "net": history["net"], "layer": history["layer"],
            "requested_layer": history["requested_layer"], "resolved_layer": history["resolved_layer"],
            "connected_layers": history["connected_layers"],
            "position_mm": history["position_mm"], "status": "solved",
            "voltage_v": history["voltage_v"][-1],
            "voltage_drop_v": history["voltage_drop_v"][-1],
            "peak_adjacent_current_a": max(history["current_a"], default=0.0),
            "peak_adjacent_current_density_a_mm2": max(history["current_density_a_mm2"], default=0.0),
        })

    if capacitance_info["status"] == "approximate":
        issues.append(ValidationIssue(
            "TRANSIENT_CAPACITANCE_APPROXIMATE",
            "warning",
            f"Distributed capacitance uses a stackup-derived single-reference quasi-static estimate ({capacitance_info['total_capacitance_f'] * 1e12:.6g} pF total).",
            suggestion="Run a mesh/stackup sensitivity study and compare critical nets against a validated 2.5D or full-wave extraction.",
            status="approximate",
        ))
        if capacitance_info["reference_mode"] == "implicit_nearest_copper":
            issues.append(ValidationIssue(
                "TRANSIENT_CAPACITANCE_IMPLICIT_REFERENCE",
                "warning",
                "Capacitance is referenced to the nearest stackup copper because no explicit return conductor was selected.",
                suggestion="Select and anchor the actual return/ground net for a physically traceable distributed capacitance model.",
                status="approximate",
            ))
        if int(capacitance_info["skipped_via_branch_count"]) > 0:
            issues.append(ValidationIssue(
                "TRANSIENT_VIA_CAPACITANCE_UNSUPPORTED",
                "warning",
                "Via barrel capacitance is not included in the current stackup-shunt approximation.",
                suggestion="Use a validated via field model or provide an explicit lumped via capacitance.",
                status="unsupported",
            ))
    else:
        issues.append(ValidationIssue(
            "TRANSIENT_CAPACITANCE_UNSUPPORTED",
            "warning",
            str(capacitance_info.get("reason", "No compatible stackup/reference geometry was available for distributed capacitance.")),
            suggestion="Import dielectric thickness/permittivity and select a return conductor, or use a validated RLC/full-wave plugin.",
            status="unsupported",
        ))
    issues.extend([
        ValidationIssue(
            "PEEC_RLC_TRANSIENT_EXPERIMENTAL",
            "warning",
            "The transient result uses backward Euler with extracted conductor resistance, the full partial-inductance matrix, and capability-gated distributed capacitance.",
            status="approximate",
        ),
        ValidationIssue(
            "TRANSIENT_DIELECTRIC_LOSS_UNSUPPORTED",
            "warning",
            "Dielectric loss, dispersive materials, radiation, and full-wave transmission-line propagation are not included.",
            suggestion="Use a validated broadband or full-wave plugin when those effects matter.",
            status="unsupported",
        ),
        ValidationIssue(
            "TRANSIENT_DEVICE_DYNAMICS_UNSUPPORTED",
            "warning",
            "Sources and loads are imposed waveforms; regulator control loops, switch models, nonlinear devices, and package parasitics are not inferred.",
            suggestion="Assign explicit SPICE or behavioral models for closed-loop device simulation.",
            status="unsupported",
        ),
        ValidationIssue(
            "VIA_PLATING_ASSUMPTION",
            "warning",
            f"Via barrels without fabrication plating data use {float(spec.mesh.get('via_plating_thickness_mm', 0.025)):.4g} mm plating.",
            status="approximate",
        ),
    ])
    solve_elapsed_s = perf_counter() - solve_started
    actual_dense_array_bytes = int(sum(array.nbytes for array in (
        physical_inductance, physical_resistance, inductance, resistance, capacitance,
        incidence, dynamic_matrix, unknown_capacitance, known_capacitance,
    )))
    stored_numeric_value_count = sum(
        sum(len(values) for values in frame_value["scalar_values"].values())
        + sum(len(values) for values in frame_value["vector_values"].values())
        for frame_value in frames
    )
    stored_numeric_bytes = stored_numeric_value_count * 8
    visualization_ranges = {}
    for field in field_layouts:
        values = [sample for frame_value in frames for sample in frame_value["scalar_values"].get(field, [])]
        if values:
            visualization_ranges[field] = {"minimum": float(min(values)), "maximum": float(max(values))}
    return AnalysisResult(
        analysis_id=spec.analysis_id or "peec-rl-transient",
        mode=spec.mode,
        status="completed",
        model_status="approximate",
        summary={
            "source_voltage_v": max((waveform_value(item, settings.stop_time_s) for item, _, _ in source_locations), default=0.0),
            "max_voltage_drop_v": max(0.0, max_drop),
            "max_voltage_overshoot_v": max(0.0, max_overshoot),
            "max_current_density_a_mm2": max_density,
            "peak_branch_current_a": max_current,
            "peak_copper_loss_w": max_loss,
            "peak_inductive_drop_v": peak_inductive_drop,
            "peak_capacitive_current_a": peak_capacitive_current,
            "estimated_distributed_capacitance_f": float(capacitance_info["total_capacitance_f"]),
            "fastest_extracted_lc_characteristic_s": fastest_lc_time_s,
            "max_scaled_linear_residual": max_scaled_residual,
            "inductance_passivity_correction_ratio": correction_ratio,
            "inductance_negative_eigenmodes": int(passivity["negative_eigenmode_count"]),
            "node_count": len(physical_node_ids),
            "branch_count": physical_count,
            "contact_branch_count": len(contact_resistances),
            "matrix_order": dynamic_matrix.shape[0],
            "geometry_counts": mesh.geometry_counts,
            "stop_time_s": settings.stop_time_s,
            "requested_time_step_s": settings.requested_time_step_s,
            "recommended_time_step_s": recommend_time_step_s(spec),
            "time_step_mode": settings.time_step_mode,
            "time_step_s": settings.time_step_s,
            "internal_step_count": settings.internal_steps,
            "requested_output_decimation": settings.requested_output_decimation,
            "output_decimation": settings.output_decimation,
            "output_decimation_mode": settings.output_decimation_mode,
            "frame_count": len(frames),
            "playback_fps": settings.playback_fps,
            "initial_condition": settings.initial_condition,
            "max_solver_time_s": settings.max_solver_time_s,
            "solve_wall_time_s": solve_elapsed_s,
            "memory_budget_bytes": settings.memory_budget_bytes,
            **resource_estimate,
            "actual_dense_array_bytes": actual_dense_array_bytes,
            "stored_transient_numeric_bytes": stored_numeric_bytes,
            "visual_node_sample_count": len(node_layout),
            "visual_branch_sample_count": len(branch_layout),
            "visualization_ranges": visualization_ranges,
        },
        fields={
            "visualization": {
                "schema": "spike/result-visualization/v1",
                "scalar_fields": final_frame["scalar_fields"],
                "vector_fields": final_frame["vector_fields"],
                "mesh": preview_cells,
                "time_series": {
                    "contract": "spike/compact-field-series/v1",
                    "times_s": times,
                    "layouts": series_layouts,
                    "field_layouts": field_layouts,
                    "vector_layouts": {"current_density": "branches"},
                    "vector_directions": {"current_density": branch_directions},
                    "frames": frames,
                },
            },
        },
        networks={
            "transient": {
                "contract": "spike/peec-rlc-transient/v2",
                "integration": "backward_euler",
                "controls": spec.transient,
                "capacitance": capacitance_info,
                "parameter_availability": {
                    "resistance": "extracted",
                    "partial_inductance": "extracted",
                    "capacitance": capacitance_info["status"],
                    "dielectric_loss": "unsupported",
                    "nonlinear_devices": "unsupported",
                },
            },
            "probe_waveforms": list(probe_history.values()),
        },
        probes=probes,
        issues=issues,
        provenance={
            "solver": "spike-peec-rlc-transient/v0.2",
            "formulation": "topology_correct_peec_rlc_backward_euler",
            "native": True,
            "epsilon_r": native_config.eps_r,
            "mesh_target_mm": mesh.target_size_mm,
            "branch_admission": dict(mesh.branch_admission),
            "transient_branch_limit": settings.max_branches,
            "transient_memory_budget_bytes": settings.memory_budget_bytes,
            "via_model": str(spec.mesh.get("via_model", "extracted")),
            "integration": "backward_euler",
            "inductance_passivity": passivity,
            "time_step_s": settings.time_step_s,
            "output_decimation": settings.output_decimation,
            "limits": [
                "quasi-static conductor R and mutual partial L",
                "single-reference stackup capacitance approximation",
                "dense PEEC matrix",
                "no dielectric loss, dispersion, radiation, or full-wave propagation",
                "no nonlinear device or control-loop dynamics",
                "ideal imposed voltage and current boundary waveforms",
            ],
        },
    )
