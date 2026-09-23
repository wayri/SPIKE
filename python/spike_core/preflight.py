"""Pre-solve validation and renderer-neutral mesh preview generation."""

from __future__ import annotations

from math import ceil, hypot
from typing import Any, Dict, Iterable, List, Tuple

from .contracts import AnalysisSpec, DesignIR, ValidationIssue
from .layers import copper_stack_profile
from .meshing import build_mesh


Point = Tuple[float, float]


def _point(value: Any) -> Point:
    if isinstance(value, dict):
        return float(value.get("x", 0)), float(value.get("y", 0))
    return float(value[0]), float(value[1])


def _net(item: Dict[str, Any]) -> str:
    return str(item.get("net_name") or item.get("net") or "")


def _point_in_polygon(point: Point, polygon: List[Point]) -> bool:
    inside = False
    x, y = point
    previous = polygon[-1]
    for current in polygon:
        denominator = previous[1] - current[1]
        intersects = (current[1] > y) != (previous[1] > y)
        if intersects and x < (previous[0] - current[0]) * (y - current[1]) / (denominator or 1e-15) + current[0]:
            inside = not inside
        previous = current
    return inside


def _distance_to_segment(point: Point, start: Point, end: Point) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if not length_squared:
        return hypot(point[0] - start[0], point[1] - start[1])
    ratio = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared))
    return hypot(point[0] - start[0] - ratio * dx, point[1] - start[1] - ratio * dy)


def _terminal_on_copper(design: DesignIR, terminal: Dict[str, Any], requested: set[str]) -> bool:
    raw_position = terminal.get("position_mm") or terminal.get("at")
    if raw_position is None:
        return False
    point = _point(raw_position)
    terminal_net = str(terminal.get("net") or terminal.get("net_name") or "")
    allowed_nets = {terminal_net} if terminal_net else requested
    layer = str(terminal.get("layer", ""))
    tolerance = max(float(terminal.get("snap_distance_mm", 2.0)), 0.01)
    for track in design.tracks:
        if allowed_nets and _net(track) not in allowed_nets:
            continue
        if layer and str(track.get("layer", "")) != layer:
            continue
        if _distance_to_segment(point, _point(track["start"]), _point(track["end"])) <= max(tolerance, float(track.get("width", 0.2)) / 2):
            return True
    for via in design.vias:
        if allowed_nets and _net(via) not in allowed_nets:
            continue
        if layer and layer not in via.get("layers", []):
            continue
        if hypot(point[0] - _point(via.get("at", (0, 0)))[0], point[1] - _point(via.get("at", (0, 0)))[1]) <= max(tolerance, float(via.get("size", 0.6)) / 2):
            return True
    for pad in design.pads:
        if allowed_nets and _net(pad) not in allowed_nets:
            continue
        layers = pad.get("layers", [pad.get("layer", "")])
        on_layer = (
            not layer
            or layer in layers
            or ("*.Cu" in layers and layer.endswith(".Cu"))
        )
        if not on_layer:
            continue
        center = _point(pad.get("at", (0, 0)))
        size = pad.get("size", [pad.get("width", 0), pad.get("height", 0)])
        width = float(size[0] if isinstance(size, (list, tuple)) else pad.get("width", 0))
        height = float(size[1] if isinstance(size, (list, tuple)) and len(size) > 1 else pad.get("height", width))
        if abs(point[0] - center[0]) <= width / 2 + tolerance and abs(point[1] - center[1]) <= height / 2 + tolerance:
            return True
    for zone in design.zones:
        if allowed_nets and _net(zone) not in allowed_nets:
            continue
        if layer and str(zone.get("layer", "")) != layer:
            continue
        polygon = [_point(value) for value in zone.get("points", [])]
        if len(polygon) >= 3 and _point_in_polygon(point, polygon):
            return True
    return False


def _layer_z(design: DesignIR) -> Dict[str, float]:
    return copper_stack_profile(design)[1]


def _track_cells(track: Dict[str, Any], target: float, z: float, index: int) -> Iterable[Dict[str, Any]]:
    start, end = _point(track["start"]), _point(track["end"])
    length = hypot(end[0] - start[0], end[1] - start[1])
    segments = max(1, int(ceil(length / target)))
    width = max(float(track.get("width", 0.2)), 0.01)
    nx = -(end[1] - start[1]) / max(length, 1e-15) * width / 2
    ny = (end[0] - start[0]) / max(length, 1e-15) * width / 2
    for segment in range(segments):
        a = segment / segments
        b = (segment + 1) / segments
        p0 = (start[0] + (end[0] - start[0]) * a, start[1] + (end[1] - start[1]) * a)
        p1 = (start[0] + (end[0] - start[0]) * b, start[1] + (end[1] - start[1]) * b)
        yield {
            "id": f"track-{index + 1}-cell-{segment + 1}",
            "kind": "surface",
            "source_kind": "track",
            "source_id": track.get("id", f"track-{index + 1}"),
            "layer": str(track.get("layer", "F.Cu")),
            "net": _net(track),
            "vertices_mm": [
                [p0[0] + nx, p0[1] + ny, z],
                [p1[0] + nx, p1[1] + ny, z],
                [p1[0] - nx, p1[1] - ny, z],
                [p0[0] - nx, p0[1] - ny, z],
            ],
        }


def build_mesh_preview(design: DesignIR, spec: AnalysisSpec) -> Dict[str, Any]:
    """Build the versioned mesh representation used by preview and plugins."""

    return build_mesh(design, spec)


def preflight_analysis(design: DesignIR, spec: AnalysisSpec, solver_catalog: List[Dict[str, Any]]) -> Dict[str, Any]:
    issues: List[ValidationIssue] = []
    from .importers import import_analysis_blockers
    issues.extend(ValidationIssue("IMPORT_NOT_SOLVER_READY", "error", reason) for reason in import_analysis_blockers(design, spec.mode))
    configured_memory_gb = spec.mesh.get("solver_memory_limit_gb")
    if configured_memory_gb is not None:
        try:
            configured_memory_gb = float(configured_memory_gb)
        except (TypeError, ValueError):
            configured_memory_gb = 0.0
        if configured_memory_gb < 2.0:
            issues.append(ValidationIssue(
                "SOLVER_MEMORY_LIMIT_INVALID",
                "error",
                "Solver memory limit must be at least 2 GB.",
                suggestion="Set the solver memory limit to 2 GB or more in Settings or in the analysis request.",
            ))
    available_nets = {str(item.get("name", "")) for item in design.nets}
    requested = {name for name in spec.net_names if name}
    missing_nets = sorted(requested - available_nets)
    if not requested:
        issues.append(ValidationIssue("NET_SELECTION_REQUIRED", "error", "Select at least one analysis net."))
    if missing_nets:
        issues.append(ValidationIssue("NET_NOT_FOUND", "error", f"Selected nets are not present in DesignIR: {', '.join(missing_nets)}."))

    selected_geometry = [
        item for collection in (design.tracks, design.vias, design.pads, design.zones)
        for item in collection if not requested or _net(item) in requested
    ]
    if not selected_geometry:
        issues.append(ValidationIssue("NO_SELECTED_GEOMETRY", "error", "No copper geometry matches the selected nets."))

    technology = str(design.technology or design.metadata.get("technology", "rigid")).lower()
    rigid_flex_regions = list(design.regions or design.metadata.get("regions", []))
    bend_lines = list(design.bends or design.metadata.get("bends", []))
    runnable_states = {"available", "experimental"}

    def solver_supports(capability: str) -> bool:
        return any(
            item.get("state") in runnable_states
            and (spec.solver_id == "auto" or item.get("id") == spec.solver_id)
            and spec.mode in item.get("analyses", [])
            and (spec.formulation == "auto" or spec.formulation in item.get("formulations", []))
            and capability in item.get("capabilities", [])
            for item in solver_catalog
        )

    malformed_regions = [region for region in rigid_flex_regions if len(region.get("outline", [])) < 3]
    if malformed_regions:
        issues.append(ValidationIssue(
            "RIGID_FLEX_REGION_INVALID",
            "error",
            f"{len(malformed_regions)} rigid-flex region outline(s) are not closed polygons.",
            suggestion="Repair or redraw the rigid/flex region outlines before meshing.",
        ))
    geometry_state = str(spec.options.get("geometry_state", "flat")).lower()
    if technology in {"flex", "rigid-flex"} and bend_lines and geometry_state == "deformed" and not solver_supports("deformed_rigid_flex"):
        issues.append(ValidationIssue(
            "DEFORMED_RIGID_FLEX_UNSUPPORTED",
            "error",
            "The selected solver cannot analyze copper on deformed rigid-flex geometry.",
            suggestion="Run the documented flat-reference analysis or install a solver that declares deformed_rigid_flex capability.",
        ))
    elif technology in {"flex", "rigid-flex"} and bend_lines:
        issues.append(ValidationIssue(
            "RIGID_FLEX_FLAT_REFERENCE",
            "warning",
            f"{len(bend_lines)} bend definition(s) are retained, but this run uses the flat fabrication reference geometry.",
            suggestion="Use deformed geometry only with a solver that explicitly validates bend strain and nonplanar coupling.",
            status="approximate",
        ))
    if technology == "rigid-flex" and spec.mode in {"ac", "broadband_hf", "si"}:
        uniform_global = str(spec.options.get("rigid_flex_stackup_policy", "")).lower() == "uniform_global"
        regional_stackups = [region for region in rigid_flex_regions if region.get("kind") in {"flex", "transition"} and region.get("stackup")]
        if not uniform_global and not regional_stackups:
            issues.append(ValidationIssue(
                "RIGID_FLEX_REGIONAL_STACKUP_REQUIRED",
                "error",
                "Rigid-flex AC/HF analysis requires an explicit stackup for each flex/transition region or a deliberate uniform-global-stackup policy.",
                suggestion="Assign regional copper/dielectric stacks in the project before frequency-domain extraction.",
            ))
        elif not solver_supports("regional_stackup"):
            issues.append(ValidationIssue(
                "RIGID_FLEX_SOLVER_CAPABILITY_REQUIRED",
                "error",
                "The selected solver does not declare regional_stackup capability for rigid-flex frequency-domain analysis.",
                suggestion="Select a validated regional-stackup solver plugin.",
            ))
    elif technology == "rigid-flex" and spec.mode in {"dc", "transient"}:
        issues.append(ValidationIssue(
            "RIGID_FLEX_PLANAR_COPPER_MODEL",
            "warning",
            "The connected copper is solved in the flat fabrication reference; bend strain and deformation-dependent resistance are not included.",
            suggestion="Treat this result as planar unless regional copper thickness and a deformed-capable solver are configured.",
            status="approximate",
        ))
    if spec.mode in {"dc", "transient"}:
        mode_name = "Transient" if spec.mode == "transient" else "DC"
        if not spec.sources:
            issues.append(ValidationIssue("SOURCE_REQUIRED", "error", f"{mode_name} analysis requires at least one voltage source."))
        if not spec.loads:
            issues.append(ValidationIssue("LOAD_REQUIRED", "error", f"{mode_name} analysis requires at least one current load."))
        for source in spec.sources:
            if not _terminal_on_copper(design, source, requested):
                source_id = str(source.get("id", "unnamed"))
                issues.append(ValidationIssue(
                    "SPIKE-BE-PI-E-0001",
                    "error",
                    f"Source {source_id} cannot snap to selected copper.",
                    path=f"analysis.sources[{source_id}]",
                    suggestion="Pick a pad, via, zone, or exact coordinate on the source net, then validate the setup again.",
                ))
        for load in spec.loads:
            if not _terminal_on_copper(design, load, requested):
                load_id = str(load.get("id", "unnamed"))
                issues.append(ValidationIssue(
                    "SPIKE-BE-PI-E-0001",
                    "error",
                    f"Load {load_id} cannot snap to selected copper.",
                    path=f"analysis.loads[{load_id}]",
                    suggestion="Pick a pad, via, zone, or exact coordinate on the load net, then validate the setup again.",
                ))
        return_mode = str(spec.return_path.get("mode", "implicit"))
        if return_mode in {"explicit", "isolated_secondary"}:
            return_net = str(spec.return_path.get("net", ""))
            source_returns = [item for item in spec.sources if item.get("terminal_role") == "source_return"]
            load_returns = [item for item in spec.loads if item.get("terminal_role") == "load_return"]
            positive_loads = [item for item in spec.loads if item.get("terminal_role", "load_positive") != "load_return"]
            if not return_net or return_net not in requested:
                issues.append(ValidationIssue("RETURN_NET_REQUIRED", "error", "Explicit return solving requires a selected return/ground net in the analysis net set."))
            if not source_returns:
                issues.append(ValidationIssue("RETURN_SOURCE_REQUIRED", "error", "Place a source return/reference terminal on the selected return conductor."))
            if len(load_returns) != len(positive_loads):
                issues.append(ValidationIssue("RETURN_LOAD_PAIR_REQUIRED", "error", "Each current sink requires one paired return terminal."))
            positive_pairs = {str(item.get("pair_id", "")) for item in positive_loads}
            return_pairs = {str(item.get("pair_id", "")) for item in load_returns}
            if "" in positive_pairs or positive_pairs != return_pairs:
                issues.append(ValidationIssue("RETURN_PAIR_MISMATCH", "error", "Supply and return load terminals must have matching pair IDs."))
            if return_mode == "isolated_secondary":
                issues.append(ValidationIssue(
                    "ISOLATED_SECONDARY_LOCAL_REFERENCE",
                    "warning",
                    "The secondary return is a local numerical reference and remains galvanically isolated from primary ground.",
                    suggestion="Use a coupled transformer/SPICE model when primary behavior, leakage, saturation, or interwinding capacitance matters.",
                    status="approximate",
                ))
    if spec.mode in {"ac", "broadband_hf", "si"} and (not spec.frequency_start_hz or not spec.frequency_stop_hz):
        issues.append(ValidationIssue("FREQUENCY_SWEEP_REQUIRED", "error", "Frequency-domain analysis requires a positive start and stop frequency."))
    if spec.mode in {"ac", "broadband_hf", "si"}:
        dielectrics = [
            layer for layer in design.stackup
            if not str(layer.get("name", "")).endswith(".Cu")
            and (layer.get("epsilon_r") is not None or layer.get("epsilonR") is not None)
        ]
        if not dielectrics:
            issues.append(ValidationIssue("DIELECTRIC_MODEL_REQUIRED", "error", "2.5D/HF analysis requires dielectric thickness and relative permittivity."))
    if spec.mode == "transient":
        from .transient_peec import validate_transient_spec

        issues.extend(validate_transient_spec(spec))

    solver = next((item for item in solver_catalog if item.get("id") == spec.solver_id), None)
    runnable = {"available", "experimental"}
    if spec.solver_id != "auto":
        if solver is None:
            issues.append(ValidationIssue("SOLVER_NOT_FOUND", "error", f"Solver plugin {spec.solver_id} is not registered."))
        elif solver.get("state") not in runnable:
            issues.append(ValidationIssue("SOLVER_NOT_RUNNABLE", "error", f"{solver.get('name', spec.solver_id)} is {solver.get('state')}."))
    elif not any(
        item.get("state") in runnable
        and spec.mode in item.get("analyses", [])
        and (spec.formulation == "auto" or spec.formulation in item.get("formulations", []))
        and set(spec.required_capabilities).issubset(set(item.get("capabilities", [])))
        for item in solver_catalog
    ):
        issues.append(ValidationIssue("NO_COMPATIBLE_SOLVER", "error", f"No runnable solver supports {spec.mode}."))

    mesh = build_mesh_preview(design, spec)
    existing_codes = {issue.code for issue in issues}
    for mesh_issue in mesh.get("issues", []):
        if mesh_issue.get("code") not in existing_codes:
            issues.append(ValidationIssue(**mesh_issue))
            existing_codes.add(mesh_issue.get("code"))
    if mesh["truncated"]:
        admission = mesh.get("preview_admission", {})
        memory_limited = bool(admission.get("limited_by_memory"))
        issues.append(ValidationIssue(
            "MESH_PREVIEW_MEMORY_LIMIT" if memory_limited else "MESH_PREVIEW_TRUNCATED",
            "warning",
            (
                f"Mesh preview admitted {admission.get('admitted_cells', mesh['cell_count'])} of "
                f"{admission.get('requested_cells', mesh['cell_count'])} requested cells under the configured memory budget."
                if memory_limited
                else f"Mesh preview reached the {mesh['cell_count']} cell display or conductor limit."
            ),
            suggestion=(
                "Increase the solver memory budget only when system resources permit, or coarsen/isolate the selected geometry."
                if memory_limited
                else "Increase target_size_mm, restrict the selected nets, or review the conductor limit."
            ),
            status="approximate",
        ))
    if mesh["cell_count"] == 0:
        issues.append(ValidationIssue("EMPTY_MESH", "error", "Meshing produced no cells for the selected geometry."))

    transient_summary: Dict[str, Any] = {}
    if spec.mode == "transient":
        try:
            from .transient_peec import recommend_time_step_s, transient_settings

            transient_value = transient_settings(spec)
            preview_nodes = max(int(mesh.get("node_count", 0)), 1)
            preview_branches = max(int(mesh.get("branch_count", 0)), 1)
            visual_samples = min(preview_nodes + preview_branches, transient_value.visual_sample_limit)
            frame_count = int(ceil(transient_value.internal_steps / transient_value.output_decimation)) + 1
            transient_summary = {
                "recommended_time_step_s": recommend_time_step_s(spec),
                "effective_time_step_s": transient_value.time_step_s,
                "internal_step_count": transient_value.internal_steps,
                "effective_output_decimation": transient_value.output_decimation,
                "estimated_frame_count": frame_count,
                "estimated_compact_numeric_bytes": frame_count * visual_samples * 6 * 8,
                "memory_budget_bytes": transient_value.memory_budget_bytes,
                "max_solver_time_s": transient_value.max_solver_time_s,
            }
        except (TypeError, ValueError):
            pass

    errors = sum(issue.severity == "error" for issue in issues)
    return {
        "contract": "spike/preflight/v1",
        "status": "blocked" if errors else "ready",
        "can_solve": errors == 0,
        "issues": [issue.__dict__ for issue in issues],
        "mesh": mesh,
        "summary": {
            "errors": errors,
            "warnings": sum(issue.severity == "warning" for issue in issues),
            "selected_geometry_count": len(selected_geometry),
            "mesh_cell_count": mesh["cell_count"],
            "mesh_requested_preview_cells": mesh.get("preview_admission", {}).get("requested_cells", mesh["cell_count"]),
            "mesh_admitted_preview_cells": mesh.get("preview_admission", {}).get("admitted_cells", mesh["cell_count"]),
            "mesh_memory_budget_bytes": mesh.get("preview_admission", {}).get("memory_budget_bytes", 0),
            "estimated_matrix_unknowns": mesh["estimated_matrix_unknowns"],
            **transient_summary,
        },
    }
