"""Physical-input, resource, and normalized-result gates for openEMS."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from .contracts import AnalysisSpec, DesignIR


DEFAULT_CELL_LIMIT = 25_000_000
HARD_CELL_LIMIT = 200_000_000
DEFAULT_MEMORY_LIMIT = 8 * 1024**3
HARD_MEMORY_LIMIT = 64 * 1024**3
ESTIMATED_BYTES_PER_CELL = 256
FAR_FIELD_REQUEST_CONTRACT = "spike/openems-far-field-request/v1"
FAR_FIELD_RESULT_CONTRACT = "spike/openems-far-field-result/v1"
DEFAULT_FAR_FIELD_SAMPLE_LIMIT = 250_000
HARD_FAR_FIELD_SAMPLE_LIMIT = 1_000_000
MAX_FAR_FIELD_FREQUENCIES = 64
MAX_THETA_SAMPLES = 721
MAX_PHI_SAMPLES = 1_441
_BOUNDARY = re.compile(r"^(PEC|PMC|MUR|PML_[1-9][0-9]?)$")
_S_PARAMETER = re.compile(r"^s([1-9][0-9]*)([1-9][0-9]*)$")


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _point(value: Any) -> tuple[float, float] | None:
    if isinstance(value, dict):
        x, y = _number(value.get("x")), _number(value.get("y"))
    elif isinstance(value, (list, tuple)) and len(value) >= 2:
        x, y = _number(value[0]), _number(value[1])
    else:
        return None
    return (x, y) if math.isfinite(x) and math.isfinite(y) else None


def _positive(value: Any, maximum: float = 1e9) -> bool:
    number = _number(value)
    return math.isfinite(number) and 0 < number <= maximum


def _sampling_axis(
    value: Any,
    *,
    label: str,
    minimum: float,
    maximum: float,
    maximum_points: int,
    errors: List[Dict[str, str]],
) -> List[float]:
    if not isinstance(value, dict):
        errors.append({"code": f"OPENEMS_FAR_FIELD_{label.upper()}_INVALID", "message": f"Far-field {label} sampling needs start_deg, stop_deg, and points."})
        return []
    start = _number(value.get("start_deg"))
    stop = _number(value.get("stop_deg"))
    try:
        points = int(value.get("points", 0))
    except (TypeError, ValueError, OverflowError):
        points = 0
    if (
        not math.isfinite(start)
        or not math.isfinite(stop)
        or start < minimum
        or stop > maximum
        or stop <= start
        or not 2 <= points <= maximum_points
    ):
        errors.append({
            "code": f"OPENEMS_FAR_FIELD_{label.upper()}_INVALID",
            "message": f"Far-field {label} must increase within {minimum:g} to {maximum:g} degrees and contain 2 to {maximum_points:,} points.",
        })
        return []
    if label == "phi" and stop - start > 360:
        errors.append({"code": "OPENEMS_FAR_FIELD_PHI_INVALID", "message": "Far-field phi sampling cannot span more than 360 degrees."})
        return []
    return [start + (stop - start) * index / (points - 1) for index in range(points)]


def validate_far_field_request(
    request: Any,
    *,
    frequency_start_hz: Any,
    frequency_stop_hz: Any,
    options: Dict[str, Any] | None = None,
    simulation_bounds_mm: Dict[str, Any] | None = None,
    mesh_resolution_mm: Any = None,
) -> Dict[str, Any]:
    """Validate and normalize the opt-in NF2FF request without claiming solver validity."""
    if request is None:
        return {"enabled": False, "errors": [], "request": None, "resources": {"samples": 0, "estimated_numeric_bytes": 0}}
    errors: List[Dict[str, str]] = []
    if not isinstance(request, dict):
        return {
            "enabled": True,
            "errors": [{"code": "OPENEMS_FAR_FIELD_REQUEST_INVALID", "message": "Far-field request must be a JSON object."}],
            "request": None,
            "resources": {"samples": 0, "estimated_numeric_bytes": 0},
        }
    if request.get("contract") != FAR_FIELD_REQUEST_CONTRACT:
        errors.append({"code": "OPENEMS_FAR_FIELD_CONTRACT_INVALID", "message": f"Far-field request contract must be {FAR_FIELD_REQUEST_CONTRACT}."})

    raw_frequencies = request.get("frequencies_hz")
    frequencies = [_number(value) for value in raw_frequencies] if isinstance(raw_frequencies, list) else []
    sweep_start, sweep_stop = _number(frequency_start_hz), _number(frequency_stop_hz)
    if (
        not 1 <= len(frequencies) <= MAX_FAR_FIELD_FREQUENCIES
        or any(not math.isfinite(value) or value <= 0 for value in frequencies)
        or any(left >= right for left, right in zip(frequencies, frequencies[1:]))
        or not math.isfinite(sweep_start)
        or not math.isfinite(sweep_stop)
        or any(value < sweep_start or value > sweep_stop for value in frequencies)
    ):
        errors.append({
            "code": "OPENEMS_FAR_FIELD_FREQUENCIES_INVALID",
            "message": f"Far-field frequencies must contain 1 to {MAX_FAR_FIELD_FREQUENCIES} finite, strictly increasing samples inside the excitation sweep.",
        })

    theta = _sampling_axis(
        request.get("theta"), label="theta", minimum=0, maximum=180,
        maximum_points=MAX_THETA_SAMPLES, errors=errors,
    )
    phi = _sampling_axis(
        request.get("phi"), label="phi", minimum=-360, maximum=360,
        maximum_points=MAX_PHI_SAMPLES, errors=errors,
    )
    radius_m = _number(request.get("radius_m"))
    if not math.isfinite(radius_m) or not 1e-6 <= radius_m <= 1e6:
        errors.append({"code": "OPENEMS_FAR_FIELD_RADIUS_INVALID", "message": "Far-field radius must be finite and between 1 um and 1,000 km."})
    raw_center = request.get("center_mm")
    center = [_number(value) for value in raw_center] if isinstance(raw_center, (list, tuple)) and len(raw_center) == 3 else []
    if len(center) != 3 or any(not math.isfinite(value) or abs(value) > 1e9 for value in center):
        errors.append({"code": "OPENEMS_FAR_FIELD_CENTER_INVALID", "message": "Far-field phase center must contain three finite millimetre coordinates."})
    elif isinstance(simulation_bounds_mm, dict):
        lower, upper = simulation_bounds_mm.get("start"), simulation_bounds_mm.get("stop")
        if (
            not isinstance(lower, list) or not isinstance(upper, list)
            or len(lower) != 3 or len(upper) != 3
            or any(not _number(lo) < value < _number(hi) for value, lo, hi in zip(center, lower, upper))
        ):
            errors.append({"code": "OPENEMS_FAR_FIELD_CENTER_OUTSIDE_BOX", "message": "Far-field phase center must be strictly inside the FDTD/NF2FF recording volume."})

    options = options or {}
    try:
        sample_limit = int(options.get("max_far_field_samples", DEFAULT_FAR_FIELD_SAMPLE_LIMIT))
    except (TypeError, ValueError, OverflowError):
        sample_limit = 0
    if not 1 <= sample_limit <= HARD_FAR_FIELD_SAMPLE_LIMIT:
        errors.append({
            "code": "OPENEMS_FAR_FIELD_SAMPLE_LIMIT_INVALID",
            "message": f"Far-field sample limit must be between 1 and {HARD_FAR_FIELD_SAMPLE_LIMIT:,}.",
        })
    samples = len(frequencies) * len(theta) * len(phi)
    if sample_limit > 0 and samples > sample_limit:
        errors.append({
            "code": "OPENEMS_FAR_FIELD_SAMPLE_BUDGET_EXCEEDED",
            "message": f"Far-field request contains {samples:,} samples, above the configured {sample_limit:,}-sample limit.",
        })
    mesh = _number(mesh_resolution_mm)
    air = _number(options.get("air_padding_mm"))
    if math.isfinite(mesh) and mesh > 0 and math.isfinite(air) and air < 4 * mesh:
        errors.append({
            "code": "OPENEMS_FAR_FIELD_PADDING_INSUFFICIENT",
            "message": "NF2FF recording requires at least four configured mesh cells between selected conductors and the simulation boundary.",
        })
    boundaries = options.get("boundary_conditions", ["PML_8"] * 6)
    if isinstance(boundaries, list) and len(boundaries) == 6 and any(str(value) == "PEC" or str(value) == "PMC" for value in boundaries):
        errors.append({
            "code": "OPENEMS_FAR_FIELD_BOUNDARY_UNSUPPORTED",
            "message": "This NF2FF adapter requires radiating MUR or PML boundaries on all six faces; PEC/PMC mirroring is not implemented.",
        })

    normalized = None if errors else {
        "contract": FAR_FIELD_REQUEST_CONTRACT,
        "frequencies_hz": frequencies,
        "theta_deg": theta,
        "phi_deg": phi,
        "radius_m": radius_m,
        "center_mm": center,
        "shape": [len(frequencies), len(theta), len(phi)],
    }
    return {
        "enabled": True,
        "errors": errors,
        "request": normalized,
        "resources": {
            "samples": samples,
            "sample_limit": sample_limit,
            "estimated_numeric_bytes": samples * 8 * 8,
        },
    }


def _selected(values: Iterable[Dict[str, Any]], nets: set[str]) -> Iterable[Dict[str, Any]]:
    return (
        value for value in values
        if str(value.get("net_name") or value.get("net") or "") in nets
    )


def _stackup_elevations(design: DesignIR) -> Dict[str, float]:
    z = 0.0
    elevations: Dict[str, float] = {}
    for layer in design.stackup:
        name = str(layer.get("name", ""))
        kind = str(layer.get("type", "")).lower()
        conductor = kind in {"copper", "conductor"} or name.endswith(".Cu")
        dielectric = kind in {"core", "prepreg", "dielectric", "soldermask", "mask"} or "epsilon_r" in layer or "epsilonR" in layer
        if conductor:
            elevations[name] = z
        elif dielectric:
            thickness = _number(layer.get("thickness", layer.get("thickness_mm")))
            if math.isfinite(thickness) and thickness > 0:
                z -= thickness
    return elevations


def _distance_to_segment(point: tuple[float, float], start: tuple[float, float], stop: tuple[float, float]) -> float:
    dx, dy = stop[0] - start[0], stop[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 0:
        return math.inf
    projection = max(0.0, min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared))
    closest = (start[0] + projection * dx, start[1] + projection * dy)
    return math.hypot(point[0] - closest[0], point[1] - closest[1])


def _inside_polygon(point: tuple[float, float], polygon: Sequence[tuple[float, float]]) -> bool:
    inside = False
    j = len(polygon) - 1
    for i, current in enumerate(polygon):
        previous = polygon[j]
        crosses = (current[1] > point[1]) != (previous[1] > point[1])
        if crosses:
            boundary_x = (previous[0] - current[0]) * (point[1] - current[1]) / (previous[1] - current[1]) + current[0]
            if point[0] < boundary_x:
                inside = not inside
        j = i
    return inside


def _conductor_hits(
    design: DesignIR,
    nets: set[str],
    endpoint: Sequence[float],
    tolerance: float,
) -> set[str]:
    if len(endpoint) != 3:
        return set()
    x, y, z = (_number(value) for value in endpoint)
    if not all(math.isfinite(value) for value in (x, y, z)):
        return set()
    point = (x, y)
    elevations = _stackup_elevations(design)
    hits: set[str] = set()

    def layer_matches(name: str) -> bool:
        return name in elevations and abs(z - elevations[name]) <= tolerance

    for track in _selected(design.tracks, nets):
        start, stop = _point(track.get("start")), _point(track.get("end"))
        width = _number(track.get("width"))
        if start and stop and width > 0 and layer_matches(str(track.get("layer", ""))):
            if _distance_to_segment(point, start, stop) <= width / 2 + tolerance:
                hits.add(str(track.get("net_name") or track.get("net") or ""))
    for zone in _selected(design.zones, nets):
        polygon = [_point(value) for value in zone.get("points", zone.get("polygon", []))]
        valid = [value for value in polygon if value is not None]
        if len(valid) >= 3 and len(valid) == len(polygon) and layer_matches(str(zone.get("layer", ""))):
            if _inside_polygon(point, valid):
                hits.add(str(zone.get("net_name") or zone.get("net") or ""))
    for pad in _selected(design.pads, nets):
        # Match the actual adapter contour; unsupported shapes must never supply
        # a fictitious port contact. Coordinates use DesignIR's world XY frame.
        from .openems_adapter_source import pad_polygon
        try:
            polygon = pad_polygon(pad)
        except ValueError:
            continue
        center = _point(pad.get("at"))
        size = pad.get("size")
        if not isinstance(size, (list, tuple)) or not size:
            size = [size, size]
        sx = _number(size[0]) if size else float("nan")
        sy = _number(size[1] if len(size) > 1 else size[0]) if size else float("nan")
        layers = pad.get("layers", [pad.get("layer", "")])
        if not isinstance(layers, list):
            layers = [layers]
        if "*.Cu" in layers:
            layers = list(elevations)
        if center and sx > 0 and sy > 0 and any(layer_matches(str(layer)) for layer in layers):
            vertices = list(zip(polygon[0], polygon[1]))
            inside = _inside_polygon(point, vertices) or any(
                _distance_to_segment(point, vertices[index], vertices[(index+1) % 4]) <= tolerance
                for index in range(4))
            if inside:
                hits.add(str(pad.get("net_name") or pad.get("net") or ""))
    for via in _selected(design.vias, nets):
        center = _point(via.get("at"))
        diameter = _number(via.get("size", via.get("diameter")))
        layers = via.get("layers", ["F.Cu", "B.Cu"])
        if not isinstance(layers, list) or len(layers) < 2:
            continue
        layer_z = [elevations.get(str(layer)) for layer in (layers[0], layers[-1])]
        if center and diameter > 0 and all(value is not None for value in layer_z):
            bottom, top = min(layer_z), max(layer_z)
            if bottom - tolerance <= z <= top + tolerance and math.hypot(x - center[0], y - center[1]) <= diameter / 2 + tolerance:
                hits.add(str(via.get("net_name") or via.get("net") or ""))
    return {value for value in hits if value}


def validate_port_geometry(
    design: DesignIR,
    spec: AnalysisSpec,
    ports: Sequence[Dict[str, Any]],
    mesh_resolution_mm: float,
) -> List[Dict[str, str]]:
    errors: List[Dict[str, str]] = []
    nets = {str(net) for net in spec.net_names if str(net)}
    tolerance = max(1e-6, min(abs(mesh_resolution_mm) / 4, 0.05)) if math.isfinite(mesh_resolution_mm) else 0.01
    for index, port in enumerate(ports):
        if not isinstance(port, dict):
            continue
        start, stop = port.get("start"), port.get("stop")
        if not isinstance(start, (list, tuple)) or not isinstance(stop, (list, tuple)) or len(start) != 3 or len(stop) != 3:
            continue
        start_hits = _conductor_hits(design, nets, start, tolerance)
        stop_hits = _conductor_hits(design, nets, stop, tolerance)
        if not start_hits or not stop_hits:
            missing = "start" if not start_hits else "stop"
            errors.append({"code": "OPENEMS_PORT_CONDUCTOR_REQUIRED", "message": f"Port {index + 1} {missing} does not terminate on exported conductor geometry."})
        elif not any(left != right for left in start_hits for right in stop_hits):
            errors.append({"code": "OPENEMS_PORT_TERMINALS_SHORTED", "message": f"Port {index + 1} endpoints terminate on the same electrical net."})
    return errors


def validate_physics_and_resources(
    design: DesignIR,
    spec: AnalysisSpec,
    options: Dict[str, Any],
) -> Dict[str, Any]:
    errors: List[Dict[str, str]] = []
    selected = {str(net) for net in spec.net_names if str(net)}
    epsilons: List[float] = [1.0]
    stackup_thickness = 0.0
    for index, layer in enumerate(design.stackup):
        name = str(layer.get("name") or f"layer {index + 1}")
        kind = str(layer.get("type", "")).lower()
        conductor = kind in {"copper", "conductor"} or name.endswith(".Cu")
        dielectric = kind in {"core", "prepreg", "dielectric", "soldermask", "mask"} or "epsilon_r" in layer or "epsilonR" in layer
        if not conductor and not dielectric:
            continue
        thickness = _number(layer.get("thickness", layer.get("thickness_mm")))
        if not math.isfinite(thickness) or not 0 < thickness <= 100:
            errors.append({"code": "OPENEMS_LAYER_THICKNESS_INVALID", "message": f"{name} needs a finite positive thickness no greater than 100 mm."})
        else:
            stackup_thickness += thickness
        if conductor:
            conductivity = layer.get("conductivity", layer.get("conductivity_s_m"))
            if conductivity is not None and not _positive(conductivity, 1e10):
                errors.append({"code": "OPENEMS_CONDUCTIVITY_INVALID", "message": f"{name} has an invalid conductor conductivity."})
            continue
        epsilon = _number(layer.get("epsilon_r", layer.get("epsilonR")))
        if not math.isfinite(epsilon) or not 0 < epsilon <= 10_000:
            errors.append({"code": "OPENEMS_DIELECTRIC_INVALID", "message": f"{name} needs a finite relative permittivity between 0 and 10,000."})
        else:
            epsilons.append(epsilon)
        loss = _number(layer.get("loss_tangent", layer.get("lossTangent", 0)))
        if not math.isfinite(loss) or not 0 <= loss <= 10:
            errors.append({"code": "OPENEMS_DIELECTRIC_LOSS_INVALID", "message": f"{name} has an invalid loss tangent."})

    xs: List[float] = []
    ys: List[float] = []
    invalid_geometry = 0
    for track in _selected(design.tracks, selected):
        start, end = _point(track.get("start")), _point(track.get("end"))
        width = _number(track.get("width"))
        if start is None or end is None or not math.isfinite(width) or width <= 0 or start == end:
            invalid_geometry += 1
            continue
        radius = width / 2
        xs.extend((start[0] - radius, start[0] + radius, end[0] - radius, end[0] + radius))
        ys.extend((start[1] - radius, start[1] + radius, end[1] - radius, end[1] + radius))
    for zone in _selected(design.zones, selected):
        points = [_point(point) for point in zone.get("points", zone.get("polygon", []))]
        if len(points) < 3 or any(point is None for point in points):
            invalid_geometry += 1
            continue
        xs.extend(point[0] for point in points if point is not None)
        ys.extend(point[1] for point in points if point is not None)
    for via in _selected(design.vias, selected):
        center = _point(via.get("at"))
        diameter = _number(via.get("size", via.get("diameter")))
        drill = _number(via.get("drill"))
        if center is None or not _positive(diameter, 100) or not _positive(drill, 100) or drill >= diameter:
            invalid_geometry += 1
            continue
        radius = diameter / 2
        xs.extend((center[0] - radius, center[0] + radius))
        ys.extend((center[1] - radius, center[1] + radius))
    for pad in _selected(design.pads, selected):
        center = _point(pad.get("at"))
        size = pad.get("size")
        if not isinstance(size, (list, tuple)) or not size:
            size = [size, size]
        sx = _number(size[0]) if size else float("nan")
        sy = _number(size[1] if len(size) > 1 else size[0]) if size else float("nan")
        if center is None or not _positive(sx, 1000) or not _positive(sy, 1000):
            invalid_geometry += 1
            continue
        xs.extend((center[0] - sx / 2, center[0] + sx / 2))
        ys.extend((center[1] - sy / 2, center[1] + sy / 2))
    port_zs: List[float] = []
    ports = spec.options.get("ports", [])
    if isinstance(ports, list):
        for port in ports:
            if not isinstance(port, dict):
                continue
            for endpoint in (port.get("start"), port.get("stop")):
                if not isinstance(endpoint, (list, tuple)) or len(endpoint) != 3:
                    continue
                x, y, z = (_number(value) for value in endpoint)
                if all(math.isfinite(value) for value in (x, y, z)):
                    xs.append(x)
                    ys.append(y)
                    port_zs.append(z)
    if invalid_geometry:
        errors.append({"code": "OPENEMS_GEOMETRY_INVALID", "message": f"{invalid_geometry} selected conductor objects have non-finite, degenerate, or non-positive geometry."})
    if not xs or not ys:
        return {"errors": errors, "resources": {"estimated_cells": 0, "estimated_memory_bytes": 0}}

    mesh = _number(options.get("mesh_resolution_mm", 0.5))
    stop = _number(spec.frequency_stop_hz)
    wavelength_mm = 299_792_458.0 / stop / math.sqrt(max(epsilons)) * 1000 if math.isfinite(stop) and stop > 0 else float("nan")
    default_air = min(max(wavelength_mm / 10, 5.0), 100.0) if math.isfinite(wavelength_mm) else 100.0
    air = _number(options.get("air_padding_mm", default_air))
    ratio = _number(options.get("mesh_growth_ratio", 1.4))
    end_criteria = _number(options.get("end_criteria", 1e-5))
    reference = _number(options.get("reference_impedance_ohm", 50))
    plating = _number(options.get("via_plating_thickness_mm", 0.025))
    try:
        verbosity = int(options.get("verbosity", 2))
    except (TypeError, ValueError, OverflowError):
        verbosity = -1
    if not math.isfinite(air) or not 0 <= air <= 1000:
        errors.append({"code": "OPENEMS_AIR_PADDING_INVALID", "message": "Air padding must be finite and between 0 and 1,000 mm."})
    if not math.isfinite(ratio) or not 1 < ratio <= 2:
        errors.append({"code": "OPENEMS_MESH_GROWTH_INVALID", "message": "Mesh growth ratio must be greater than 1 and no greater than 2."})
    if not math.isfinite(end_criteria) or not 1e-12 <= end_criteria <= 1:
        errors.append({"code": "OPENEMS_END_CRITERIA_INVALID", "message": "End criteria must be finite and between 1e-12 and 1."})
    if not math.isfinite(reference) or not 0 < reference <= 1e9:
        errors.append({"code": "OPENEMS_REFERENCE_IMPEDANCE_INVALID", "message": "Reference impedance must be finite and positive."})
    if not math.isfinite(plating) or not 0 < plating <= 5:
        errors.append({"code": "OPENEMS_VIA_PLATING_INVALID", "message": "Via plating thickness must be finite and between 0 and 5 mm."})
    if not 0 <= verbosity <= 3:
        errors.append({"code": "OPENEMS_VERBOSITY_INVALID", "message": "openEMS verbosity must be between 0 and 3."})
    boundaries = options.get("boundary_conditions", ["PML_8"] * 6)
    if not isinstance(boundaries, list) or len(boundaries) != 6 or any(not isinstance(item, str) or not _BOUNDARY.match(item) for item in boundaries):
        errors.append({"code": "OPENEMS_BOUNDARY_INVALID", "message": "Boundary conditions must contain six supported PEC, PMC, MUR, or PML_n values."})

    try:
        cell_limit = int(options.get("max_estimated_cells", DEFAULT_CELL_LIMIT))
        memory_limit = int(options.get("max_estimated_memory_bytes", DEFAULT_MEMORY_LIMIT))
    except (TypeError, ValueError, OverflowError):
        cell_limit, memory_limit = 0, 0
    if not 1 <= cell_limit <= HARD_CELL_LIMIT:
        errors.append({"code": "OPENEMS_CELL_LIMIT_INVALID", "message": f"Estimated-cell limit must be between 1 and {HARD_CELL_LIMIT:,}."})
    if not 64 * 1024**2 <= memory_limit <= HARD_MEMORY_LIMIT:
        errors.append({"code": "OPENEMS_MEMORY_LIMIT_INVALID", "message": "Estimated-memory limit must be between 64 MiB and 64 GiB."})

    estimated_cells = 0
    estimated_memory = 0
    simulation_bounds: Dict[str, Any] | None = None
    if math.isfinite(mesh) and mesh > 0 and math.isfinite(air) and air >= 0:
        z_min = min([-stackup_thickness, *port_zs]) if port_zs else -stackup_thickness
        z_max = max([0.0, *port_zs]) if port_zs else 0.0
        spans = (max(xs) - min(xs) + 2 * air, max(ys) - min(ys) + 2 * air, z_max - z_min + 2 * air)
        simulation_bounds = {
            "start": [min(xs) - air, min(ys) - air, z_min - air],
            "stop": [max(xs) + air, max(ys) + air, z_max + air],
        }
        ratios = [span / mesh for span in spans]
        if any(not math.isfinite(value) or value > HARD_CELL_LIMIT for value in ratios):
            errors.append({"code": "OPENEMS_RESOURCE_EXTENT_INVALID", "message": "Conductor or port extents exceed the bounded FDTD resource estimator."})
        else:
            counts = [max(2, math.ceil(value) + 1) for value in ratios]
            estimated_cells = math.prod(counts)
            estimated_memory = estimated_cells * ESTIMATED_BYTES_PER_CELL
            if cell_limit > 0 and estimated_cells > cell_limit:
                errors.append({"code": "OPENEMS_CELL_BUDGET_EXCEEDED", "message": f"Estimated FDTD grid is {estimated_cells:,} cells, above the configured {cell_limit:,}-cell limit."})
            if memory_limit > 0 and estimated_memory > memory_limit:
                errors.append({"code": "OPENEMS_MEMORY_BUDGET_EXCEEDED", "message": f"Estimated FDTD state is {estimated_memory / 1024**3:.2f} GiB, above the configured memory limit."})
    return {
        "errors": errors,
        "resources": {
            "estimated_cells": estimated_cells,
            "estimated_memory_bytes": estimated_memory,
            "bytes_per_cell_assumption": ESTIMATED_BYTES_PER_CELL,
            "cell_limit": cell_limit,
            "memory_limit_bytes": memory_limit,
            "air_padding_mm": air,
            "simulation_bounds_mm": simulation_bounds,
        },
    }


def validate_normalized_result(
    result: Any,
    *,
    setup_only: bool,
    expected_points: int,
    expected_start_hz: float,
    expected_stop_hz: float,
    expected_job_id: str,
    expected_input_digest: str,
    expected_run_id: str,
    ports: Sequence[Dict[str, Any]],
    root: Path,
    expected_far_field: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError("Normalized result must be a JSON object.")
    if result.get("contract") != "spike/external-result/v1" or result.get("engine_id") != "external.openems":
        raise ValueError("Normalized result contract or engine ID is invalid.")
    expected_status = "setup_completed" if setup_only else "completed"
    expected_model_status = "unvalidated" if expected_far_field is not None and not setup_only else "approximate"
    if result.get("status") != expected_status or result.get("model_status") != expected_model_status:
        raise ValueError(f"Normalized result must report {expected_status} with {expected_model_status} model status.")
    mesh = result.get("mesh")
    if not isinstance(mesh, dict) or not _positive(mesh.get("resolution_mm"), 1000):
        raise ValueError("Normalized result is missing a finite positive mesh resolution.")
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("Normalized result must list its generated artifacts.")
    for artifact in artifacts:
        artifact_path = (root / artifact).resolve() if isinstance(artifact, str) and artifact else None
        if artifact_path is None or not artifact_path.is_relative_to(root) or not artifact_path.exists():
            raise ValueError("Normalized result contains an invalid artifact path.")
    binding = result.get("run_binding")
    if not isinstance(binding, dict):
        raise ValueError("Normalized result is missing its execution binding.")
    if (
        str(binding.get("job_id", "")) != expected_job_id
        or str(binding.get("input_digest", "")) != expected_input_digest
        or str(binding.get("run_id", "")) != expected_run_id
    ):
        raise ValueError("Normalized result does not belong to this job execution.")
    if not math.isclose(_number(binding.get("mesh_resolution_mm")), _number(mesh.get("resolution_mm")), rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("Normalized result mesh metadata is internally inconsistent.")
    if (
        not math.isclose(_number(binding.get("frequency_start_hz")), expected_start_hz, rel_tol=1e-12, abs_tol=1e-9)
        or not math.isclose(_number(binding.get("frequency_stop_hz")), expected_stop_hz, rel_tol=1e-12, abs_tol=1e-9)
        or int(binding.get("frequency_points", 0)) != expected_points
    ):
        raise ValueError("Normalized result sweep metadata does not match the requested analysis.")
    if setup_only:
        return result

    frequencies = result.get("frequency_hz")
    if not isinstance(frequencies, list) or len(frequencies) != expected_points or len(frequencies) < 2:
        raise ValueError("Normalized result frequency count does not match the requested sweep.")
    numeric_frequency = [_number(value) for value in frequencies]
    if any(not math.isfinite(value) or value <= 0 for value in numeric_frequency) or any(a >= b for a, b in zip(numeric_frequency, numeric_frequency[1:])):
        raise ValueError("Normalized result frequencies must be finite, positive, and strictly increasing.")
    expected_frequency = [
        expected_start_hz + (expected_stop_hz - expected_start_hz) * index / (expected_points - 1)
        for index in range(expected_points)
    ]
    frequency_tolerance = max(1e-9, abs(expected_stop_hz - expected_start_hz) * 1e-12)
    if any(not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=frequency_tolerance) for actual, expected in zip(numeric_frequency, expected_frequency)):
        raise ValueError("Normalized result frequency grid does not match the requested sweep.")
    excited = [index for index, port in enumerate(ports) if bool(port.get("excite", False))]
    if len(excited) != 1:
        raise ValueError("Normalized result cannot be mapped without exactly one excited port.")
    expected_columns = {f"s{index + 1}{excited[0] + 1}" for index in range(len(ports))}
    parameters = result.get("s_parameters")
    if not isinstance(parameters, dict) or set(parameters) != expected_columns:
        raise ValueError("Normalized result S-parameter columns do not match the requested ports.")
    for name, column in parameters.items():
        if not _S_PARAMETER.match(name) or not isinstance(column, dict):
            raise ValueError(f"Normalized S-parameter column {name} is invalid.")
        real, imaginary = column.get("real"), column.get("imag")
        if not isinstance(real, list) or not isinstance(imaginary, list) or len(real) != len(frequencies) or len(imaginary) != len(frequencies):
            raise ValueError(f"Normalized S-parameter column {name} has an invalid shape.")
        if any(not math.isfinite(_number(value)) for value in [*real, *imaginary]):
            raise ValueError(f"Normalized S-parameter column {name} contains a non-finite value.")
    if expected_far_field is None:
        if "far_field" in result:
            raise ValueError("Normalized result contains an unrequested far-field payload.")
    else:
        _validate_far_field_result(result.get("far_field"), expected_far_field)
    return result


def _flat_result_array(
    value: Any,
    *,
    length: int,
    label: str,
    nonnegative: bool = False,
    strictly_positive: bool = False,
) -> List[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"Normalized far-field {label} has an invalid shape.")
    numbers = [_number(item) for item in value]
    if any(not math.isfinite(item) or abs(item) > 1e300 for item in numbers):
        raise ValueError(f"Normalized far-field {label} contains a non-finite or out-of-range value.")
    if nonnegative and any(item < 0 for item in numbers):
        raise ValueError(f"Normalized far-field {label} contains a negative value.")
    if strictly_positive and any(item <= 0 for item in numbers):
        raise ValueError(f"Normalized far-field {label} must contain positive values.")
    return numbers


def _same_numeric_grid(actual: Any, expected: Sequence[float], label: str) -> None:
    values = _flat_result_array(actual, length=len(expected), label=label)
    if any(not math.isclose(value, reference, rel_tol=1e-12, abs_tol=1e-9) for value, reference in zip(values, expected)):
        raise ValueError(f"Normalized far-field {label} does not match the signed request.")


def _validate_far_field_result(payload: Any, expected: Dict[str, Any]) -> None:
    if not isinstance(payload, dict) or payload.get("contract") != FAR_FIELD_RESULT_CONTRACT:
        raise ValueError("Normalized result is missing the requested NF2FF far-field contract.")
    if payload.get("status") != "computed" or payload.get("validation_status") != "not_validated":
        raise ValueError("Normalized far-field must be computed but explicitly not validated.")
    normalization = payload.get("normalization")
    fixed = {"kind": "incident_power", "incident_power_w": 1.0,
             "incident_voltage_phase_deg": 0.0, "phasor": "peak",
             "source_spectrum": "single_sided_pulse_fourier_integral",
             "frequency_sampling": "exact_port_reevaluation"}
    if (not isinstance(normalization, dict)
            or set(normalization) != set(fixed) | {"reference_impedance_ohm"}
            or any(normalization.get(k) != v for k, v in fixed.items())
            or any(type(normalization.get(k)) not in (int, float)
                   for k in ("incident_power_w", "incident_voltage_phase_deg", "reference_impedance_ohm"))
            or not _positive(normalization.get("reference_impedance_ohm"), 1e6)):
        raise ValueError("Normalized far-field requires explicit one-watt incident-power normalization.")
    shape = expected.get("shape")
    if (
        not isinstance(shape, list) or len(shape) != 3
        or any(not isinstance(value, int) or value < 1 for value in shape)
        or math.prod(shape) > HARD_FAR_FIELD_SAMPLE_LIMIT
        or payload.get("shape") != shape
    ):
        raise ValueError("Normalized far-field shape is invalid or exceeds the hard resource limit.")
    frequencies = expected.get("frequencies_hz", [])
    theta = expected.get("theta_deg", [])
    phi = expected.get("phi_deg", [])
    _same_numeric_grid(payload.get("frequencies_hz"), frequencies, "frequency grid")
    _same_numeric_grid(payload.get("theta_deg"), theta, "theta grid")
    _same_numeric_grid(payload.get("phi_deg"), phi, "phi grid")
    if not math.isclose(_number(payload.get("radius_m")), _number(expected.get("radius_m")), rel_tol=1e-12, abs_tol=1e-12):
        raise ValueError("Normalized far-field radius does not match the signed request.")
    _same_numeric_grid(payload.get("center_mm"), expected.get("center_mm", []), "phase center")

    frequency_count, theta_count, phi_count = shape
    samples = frequency_count * theta_count * phi_count
    field = payload.get("e_field_v_m")
    if not isinstance(field, dict):
        raise ValueError("Normalized far-field electric-field arrays are missing.")
    for component in ("theta", "phi"):
        vector = field.get(component)
        if not isinstance(vector, dict):
            raise ValueError(f"Normalized far-field E-{component} array is missing.")
        _flat_result_array(vector.get("real"), length=samples, label=f"E-{component} real")
        _flat_result_array(vector.get("imag"), length=samples, label=f"E-{component} imaginary")
    _flat_result_array(field.get("magnitude"), length=samples, label="electric-field magnitude", nonnegative=True)

    directivity = payload.get("directivity")
    if not isinstance(directivity, dict):
        raise ValueError("Normalized far-field directivity arrays are missing.")
    _flat_result_array(directivity.get("linear"), length=samples, label="directivity", nonnegative=True)
    _flat_result_array(directivity.get("maximum_linear"), length=frequency_count, label="maximum directivity", strictly_positive=True)

    power = payload.get("radiated_power")
    if not isinstance(power, dict) or power.get("angular_units") != "W/sr":
        raise ValueError("Normalized far-field radiated-power arrays are missing.")
    _flat_result_array(power.get("angular_w"), length=samples, label="angular radiated power", nonnegative=True)
    _flat_result_array(power.get("total_w"), length=frequency_count, label="total radiated power", strictly_positive=True)
    validation = payload.get("validation")
    if not isinstance(validation, dict) or validation.get("status") != "not_validated":
        raise ValueError("Normalized far-field validation provenance is missing or overclaims validation.")
