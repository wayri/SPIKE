# SPDX-License-Identifier: Apache-2.0
"""Admit a bounded multilayer SpiDeR board for EMerge's planar PCB API.

Only explicit imported copper and stackup data are used. Rejected source
features would otherwise disappear from the FEM model without a warning.
"""

from __future__ import annotations

import math

from extensions.openems_suite.openems_adapter_source import pad_polygon
from extensions.emerge_suite.stackup import compile_stackup


MAX_POLYGONS = 4096
MAX_VERTICES = 200_000
MAX_SURROUNDING_BOXES = 8


def admit_conductor_loss(parameters: dict) -> None:
    """Reject finite-conductor requests until the generated model represents them."""
    enabled = parameters.get("include_conductor_loss", False)
    if not isinstance(enabled, bool):
        raise ValueError("include_conductor_loss must be a boolean.")
    model = parameters.get("conductor_loss_model", "pec")
    if not isinstance(model, str):
        raise ValueError("conductor_loss_model must be a string.")
    finite_conductor = enabled or model.strip().lower() not in {
        "", "none", "pec", "perfect_conductor",
    }
    internal_reactance = parameters.get("include_internal_reactance", False)
    if not isinstance(internal_reactance, bool):
        raise ValueError("include_internal_reactance must be a boolean.")
    finite_conductor = finite_conductor or internal_reactance
    for key in ("enable_skin_effect", "skin_effect", "include_proximity_loss", "enable_proximity_effect"):
        flag = parameters.get(key, False)
        if not isinstance(flag, bool):
            raise ValueError(f"{key} must be a boolean.")
        finite_conductor = finite_conductor or flag
    finite_conductor = finite_conductor or parameters.get("loss_model") is not None
    finite_conductor = finite_conductor or any(
        parameters.get(key) is not None
        for key in ("copper_conductivity_s_per_m", "copper_thickness_um",
                    "surface_impedance_ohm", "conductivity_s_m", "thickness_m")
    )
    roughness_model = parameters.get(
        "surface_roughness_model", parameters.get("roughness_model", "none")
    )
    if not isinstance(roughness_model, str):
        raise ValueError("roughness_model must be a string.")
    roughness = roughness_model.strip().lower() not in {"", "none", "smooth"}
    roughness = roughness or any(
        parameters.get(key) is not None
        for key in ("surface_roughness_um", "roughness_rms_um", "rms_roughness_um")
    )
    if finite_conductor or roughness:
        raise ValueError(
            "EMerge board export currently uses zero-thickness PEC copper. "
            "Finite conductivity, copper thickness, surface impedance, skin/proximity loss, "
            "and conductor roughness are unsupported; disable conductor and roughness loss "
            "requests before preparing or running this case."
        )


def number(value: object, label: str, *, low: float = -math.inf, high: float = math.inf) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{label} must be a finite number.")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{label} is out of range.") from error
    if not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"{label} must be finite and between {low:g} and {high:g}.")
    return result


def _point(value: object, label: str) -> tuple[float, float]:
    if isinstance(value, dict):
        value = [value.get("x"), value.get("y")]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{label} must contain two millimetre coordinates.")
    return number(value[0], label), number(value[1], label)


def _surroundings(value: object, bounds: list[float]) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, dict) or value.get("contract") != "spike/emerge-surroundings/v1":
        raise ValueError("Surrounding geometry needs spike/emerge-surroundings/v1.")
    objects = value.get("objects")
    if not isinstance(objects, list) or not 1 <= len(objects) <= MAX_SURROUNDING_BOXES:
        raise ValueError("Surrounding geometry needs 1–8 dielectric boxes.")
    result = []
    for index, obj in enumerate(objects):
        if not isinstance(obj, dict) or obj.get("kind") != "dielectric_box":
            raise ValueError("Only explicit dielectric_box surroundings are supported.")
        origin, size = obj.get("origin_mm"), obj.get("size_mm")
        if not isinstance(origin, (list, tuple)) or len(origin) != 3 or not isinstance(size, (list, tuple)) or len(size) != 3:
            raise ValueError("Each dielectric box needs three-dimensional origin_mm and size_mm.")
        xyz = [number(v, "dielectric box origin", low=-1000, high=1000) for v in origin]
        dimensions = [number(v, "dielectric box size", low=0.1, high=200) for v in size]
        epsilon = number(obj.get("epsilon_r"), "dielectric box relative permittivity", low=1.01, high=30)
        if xyz[2] < 0.5:
            raise ValueError("A dielectric box must begin at least 0.5 mm above top copper.")
        if xyz[2] + dimensions[2] > 200:
            raise ValueError("Dielectric box height exceeds the bounded air-domain limit.")
        if (xyz[0] + dimensions[0] < bounds[0] or xyz[0] > bounds[2]
                or xyz[1] + dimensions[1] < bounds[1] or xyz[1] > bounds[3]):
            raise ValueError("Dielectric box must overlap the antenna board in XY.")
        result.append({"kind": "dielectric_box", "name": str(obj.get("name") or f"Surrounding {index+1}")[:80],
                       "origin_mm": xyz, "size_mm": dimensions, "epsilon_r": epsilon})
    for first, a in enumerate(result):
        for b in result[first + 1:]:
            if all(a["origin_mm"][axis] < b["origin_mm"][axis] + b["size_mm"][axis]
                   and b["origin_mm"][axis] < a["origin_mm"][axis] + a["size_mm"][axis]
                   for axis in range(3)):
                raise ValueError("Dielectric boxes may touch but cannot overlap.")
    if sum(math.prod(item["size_mm"]) for item in result) > 100_000:
        raise ValueError("Total surrounding dielectric volume exceeds 100000 mm3.")
    return result


def _track_polygon(track: dict) -> list[list[float]]:
    if any(track.get(key) is not None for key in ("path", "arc", "mid", "mid_mm", "curve")):
        raise ValueError(f"Track {track.get('id', '?')} has unsupported curved geometry.")
    x1, y1 = _point(track.get("start"), "track start")
    x2, y2 = _point(track.get("end"), "track end")
    width = number(track.get("width"), "track width", low=1e-6, high=100)
    length = math.hypot(x2 - x1, y2 - y1)
    if length <= 1e-9:
        raise ValueError("Zero-length track cannot be exported as copper.")
    nx, ny = -(y2-y1) * width/(2*length), (x2-x1) * width/(2*length)
    return [[x1+nx, x2+nx, x2-nx, x1-nx],
            [y1+ny, y2+ny, y2-ny, y1-ny]]


def _zone_polygon(zone: dict) -> list[list[float]]:
    source_kind = zone.get("source_kind")
    if source_kind not in {"filled_zone", "attributed_graphic_polygon", "idealized_reference_plane"} or any(zone.get(key) for key in
            ("holes", "holes_mm", "keepouts", "cutouts", "boundary_rings")):
        raise ValueError(f"Zone {zone.get('id', '?')} needs verified filled copper without holes.")
    if source_kind == "attributed_graphic_polygon" and (zone.get("source_original_net_name") != "" or not zone.get("attribution_reason")):
        raise ValueError("Attributed copper graphics need an empty source net and a documented attribution reason.")
    if source_kind == "idealized_reference_plane" and not zone.get("attribution_reason"):
        raise ValueError("An idealized reference plane needs a documented attribution reason.")
    points = zone.get("points")
    if not isinstance(points, list) or len(points) < 3:
        raise ValueError("Filled zone requires at least three boundary points.")
    xy = [_point(point, "zone point") for point in points]
    if xy[0] == xy[-1]:
        xy.pop()  # KiCad graphics may repeat the start; EMerge closes the wire itself.
    if len(xy) < 3 or any(a == b for a, b in zip(xy, xy[1:])):
        raise ValueError("Filled copper polygon has fewer than three distinct consecutive vertices.")
    return [[point[0] for point in xy], [point[1] for point in xy]]


def _net(item: dict) -> str:
    return str(item.get("net_name") or item.get("net") or "")


def _layers(item: dict) -> list[str]:
    layers = item.get("layers", [item.get("layer")])
    if not isinstance(layers, list):
        layers = [layers]
    return [str(layer) for layer in layers]


def _port(pads: dict[str, dict], signal_id: str, return_id: str,
          signal_net: str, return_net: str, copper_layers: list[dict]) -> dict:
    signal = pads.get(signal_id)
    ground = pads.get(return_id)
    if signal is None or ground is None:
        raise ValueError("Each port needs existing signal and return pad IDs.")
    if _net(signal) != signal_net or _net(ground) != return_net:
        raise ValueError("Selected port pads do not match the signal/return nets.")
    signal_layers, ground_layers = _layers(signal), _layers(ground)
    depths = {layer["name"]: layer["z_mm"] for layer in copper_layers}
    if len(signal_layers) != 1 or len(ground_layers) != 1:
        raise ValueError("Port pads need a single explicit copper layer each.")
    signal_z, return_z = depths[signal_layers[0]], depths[ground_layers[0]]
    if signal_z <= return_z:
        raise ValueError("A vertical port needs its signal pad above its return pad.")
    names = [layer["name"] for layer in copper_layers]
    if names.index(ground_layers[0]) != names.index(signal_layers[0]) + 1:
        raise ValueError("Port pads must use adjacent copper layers to avoid crossing intermediate conductors.")
    sx, sy = _point(signal.get("at"), "signal pad center")
    gx, gy = _point(ground.get("at"), "return pad center")
    if math.hypot(sx-gx, sy-gy) > 0.05:
        raise ValueError("Signal and return pad centers must align within 0.05 mm for a vertical port.")
    signal_poly, ground_poly = pad_polygon(signal), pad_polygon(ground)
    width = min(max(signal_poly[0])-min(signal_poly[0]),
                max(ground_poly[0])-min(ground_poly[0]), 1.0)
    if width < 0.05:
        raise ValueError("Port pads need at least 0.05 mm shared X width.")
    return {"signal_pad_id": signal_id, "return_pad_id": return_id,
            "x_mm": sx, "y_mm": sy, "width_mm": width,
            "height_mm": signal_z-return_z, "z_bottom_mm": return_z,
            "signal_layer": signal_layers[0], "return_layer": ground_layers[0],
            "reference_impedance_ohm": 50.0}


def compile_board(design: dict, parameters: dict) -> dict:
    if not isinstance(design, dict) or design.get("contract") != "spike/v1" or design.get("units", "mm") != "mm":
        raise ValueError("EMerge requires a millimetre SpiDeR board.")
    admit_conductor_loss(parameters)
    signal_net = parameters.get("signal_net")
    return_net = parameters.get("return_net")
    if not isinstance(signal_net, str) or not isinstance(return_net, str) or not signal_net or not return_net or signal_net == return_net:
        raise ValueError("Choose distinct signal and return nets.")
    additional = parameters.get("additional_signal_nets", [])
    if (not isinstance(additional, list) or len(additional) > 3
            or any(not isinstance(net, str) or not net.strip() for net in additional)
            or len(set(additional)) != len(additional) or signal_net in additional or return_net in additional):
        raise ValueError("additional_signal_nets needs at most three distinct nonempty nets other than the primary and return nets.")
    signal_nets = [signal_net, *additional]
    explicit_pairs = parameters.get("port_pairs")
    if "port_pairs" in parameters:
        if not isinstance(explicit_pairs, list) or not 2 <= len(explicit_pairs) <= 8:
            raise ValueError("port_pairs needs two to eight explicit port objects.")
        endpoints = []
        represented = set()
        for pair in explicit_pairs:
            if (not isinstance(pair, dict) or set(pair) != {"signal_net", "signal_pad_id", "return_pad_id"}
                    or any(not isinstance(value, str) or not value.strip() for value in pair.values())):
                raise ValueError("Each port pair needs only nonempty signal_net, signal_pad_id, and return_pad_id strings.")
            if pair["signal_net"] not in signal_nets:
                raise ValueError("Every port pair must use an explicitly selected signal net.")
            endpoints.append(pair["signal_pad_id"])
            represented.add(pair["signal_net"])
        if len(set(endpoints)) != len(endpoints):
            raise ValueError("Multiport signal pad endpoints must not be reused.")
        if represented != set(signal_nets):
            raise ValueError("Every selected signal net needs an explicit port pair.")
    elif additional:
        raise ValueError("Additional signal nets require explicit port_pairs.")
    copper_layers, dielectric_layers = compile_stackup(design.get("stackup"), number)
    thickness = -copper_layers[-1]["z_mm"]
    epsilon = dielectric_layers[0]["epsilon_r"]
    loss = max(layer["loss_tangent"] for layer in dielectric_layers)
    geometry_backend = parameters.get("geometry_backend", "emerge")
    if geometry_backend not in {"emerge", "emcad"}:
        raise ValueError("geometry_backend must be emerge or emcad.")
    selected = {*signal_nets, return_net}
    allowed_vias = parameters.get("shorting_via_ids", [])
    if not isinstance(allowed_vias, list) or len(allowed_vias) > 16 or any(not isinstance(identity, str) or not identity for identity in allowed_vias) or len(set(allowed_vias)) != len(allowed_vias):
        raise ValueError("shorting_via_ids must be a list of at most 16 distinct source via IDs.")
    selected_vias = [via for via in design.get("vias", []) if _net(via) in selected]
    if any(str(via.get("id")) not in allowed_vias for via in selected_vias) or len(selected_vias) != len(allowed_vias):
        raise ValueError("Selected nets contain vias that are not explicitly admitted as shorting vias.")
    shorting_vias = []
    if selected_vias and len(copper_layers) > 2:
        raise ValueError("Multilayer shorting vias need resolved barrels and antipads; they are unsupported.")
    for via in selected_vias:
        if _net(via) != return_net or set(_layers(via)) != {"F.Cu", "B.Cu"}:
            raise ValueError("Only source-identified through-board return-net shorting vias are supported.")
        x, y = _point(via.get("at"), "shorting via center")
        diameter = number(via.get("size"), "shorting via diameter", low=0.05, high=5)
        drill = number(via.get("drill"), "shorting via drill", low=0, high=5)
        if drill >= diameter:
            raise ValueError("Shorting via drill must be smaller than its copper diameter.")
        shorting_vias.append({"id": via["id"], "x_mm": x, "y_mm": y,
                              "radius_mm": diameter / 2, "drill_mm": drill})
    if design.get("regions") or design.get("bends"):
        raise ValueError("Rigid-flex regions or bends are not supported by the planar adapter.")
    metadata = design.get("metadata", {})
    bounds = metadata.get("board_bounds_mm") if isinstance(metadata, dict) else None
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise ValueError("Imported board needs board_bounds_mm for its dielectric extent.")
    bounds = [number(value, "board bound") for value in bounds]
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise ValueError("Board bounds are invalid.")
    if (bounds[2]-bounds[0]) * (bounds[3]-bounds[1]) > 40000:
        raise ValueError("Board extent exceeds the 40000 mm2 adapter limit.")
    surroundings = _surroundings(parameters.get("surrounding_geometry"), bounds)
    fragment_copper = parameters.get("fragment_copper", True)
    if not isinstance(fragment_copper, bool):
        raise ValueError("fragment_copper must be a boolean.")
    polygons = []
    attributed_graphics = []
    idealized_planes = []
    pads = {}
    for kind in ("tracks", "pads", "zones"):
        rows = design.get(kind, [])
        if not isinstance(rows, list):
            raise ValueError(f"SpiDeR {kind} must be an array.")
        for row in rows:
            if not isinstance(row, dict) or _net(row) not in selected:
                continue
            identity = str(row.get("id") or row.get("source_id") or "")
            if not identity:
                raise ValueError(f"Selected {kind} object lacks a stable ID.")
            layers = _layers(row)
            if not layers or any(layer not in {item["name"] for item in copper_layers} for layer in layers):
                raise ValueError(f"{identity} uses an unsupported copper layer.")
            if kind == "tracks":
                polygon = _track_polygon(row)
            elif kind == "pads":
                polygon = pad_polygon(row)
                pads[identity] = row
            else:
                polygon = _zone_polygon(row)
                if row.get("source_kind") == "attributed_graphic_polygon":
                    attributed_graphics.append(identity)
                elif row.get("source_kind") == "idealized_reference_plane":
                    idealized_planes.append(identity)
            for layer in layers:
                polygons.append({"id": identity, "net": _net(row), "layer": layer,
                                 "xs_mm": polygon[0], "ys_mm": polygon[1]})
    if not polygons or len(polygons) > MAX_POLYGONS or sum(len(p["xs_mm"]) for p in polygons) > MAX_VERTICES:
        raise ValueError("Selected copper is empty or exceeds the polygon/vertex budget.")
    if explicit_pairs is not None:
        ports = [_port(pads, pair["signal_pad_id"], pair["return_pad_id"],
                       pair["signal_net"], return_net, copper_layers) for pair in explicit_pairs]
    else:
        port_ids = [(parameters.get("signal_pad_id"), parameters.get("return_pad_id"))]
        receive = (parameters.get("receive_signal_pad_id"), parameters.get("receive_return_pad_id"))
        if any(receive):
            if not all(receive):
                raise ValueError("Second port needs both signal and return pad IDs.")
            port_ids.append(receive)
        ports = [_port(pads, signal, ground, signal_net, return_net, copper_layers)
                 for signal, ground in port_ids]
        if len(port_ids) != len(set(port_ids)):
            raise ValueError("Ports must use distinct pad pairs.")
    port_mapping = [{"port": f"P{index}", "signal_net": _net(pads[port["signal_pad_id"]]),
                     "return_net": return_net, "signal_pad_id": port["signal_pad_id"],
                     "return_pad_id": port["return_pad_id"]} for index, port in enumerate(ports, 1)]
    fstart = number(parameters.get("frequency_start_hz"), "start frequency", low=1e8, high=1e11)
    fstop = number(parameters.get("frequency_stop_hz"), "stop frequency", low=1e8, high=1e11)
    if fstop <= fstart:
        raise ValueError("Stop frequency must exceed start frequency.")
    points = parameters.get("frequency_points")
    if isinstance(points, bool) or not isinstance(points, int) or not 2 <= points <= 64:
        raise ValueError("Frequency points must be an integer from 2 to 64.")
    resolution = number(parameters.get("mesh_resolution_mm"), "mesh resolution", low=0.05, high=10)
    planar_estimate = (bounds[2]-bounds[0]) * (bounds[3]-bounds[1]) / resolution**2
    if planar_estimate * len(dielectric_layers) > 200_000:
        raise ValueError("Board area and mesh resolution exceed the 200000-cell planar preflight budget.")
    include_loss = parameters.get("include_dielectric_loss", False)
    parallel = parameters.get("parallel", False)
    sparse_solver = parameters.get("sparse_solver", "auto")
    if sparse_solver not in {"auto", "superlu"}:
        raise ValueError("Sparse solver must be auto or superlu.")
    nearfield_enabled = parameters.get("nearfield_enabled", False)
    if any(not isinstance(value, bool) for value in (include_loss, parallel, nearfield_enabled)):
        raise ValueError("Dielectric loss, parallel, and nearfield controls must be booleans.")
    impedance = number(parameters.get("reference_impedance_ohm", 50), "reference impedance", low=1, high=1000)
    for port in ports:
        port["reference_impedance_ohm"] = impedance
    workers = parameters.get("n_workers", 2)
    excited_port = parameters.get("field_excited_port", 1)
    if isinstance(excited_port, bool) or not isinstance(excited_port, int) or not 1 <= excited_port <= len(ports):
        raise ValueError("Field excited port must identify an admitted port.")
    grid_points = parameters.get("nearfield_grid_points", 11)
    for value, label, maximum in ((workers, "n_workers", 8), (grid_points, "nearfield_grid_points", 41)):
        if isinstance(value, bool) or not isinstance(value, int) or not (1 if label == "n_workers" else 3) <= value <= maximum:
            raise ValueError(f"{label} is outside its bounded integer range.")
    if nearfield_enabled and grid_points * grid_points * points > 100_000:
        raise ValueError("Frequency and near-field grids exceed the 100000-sample budget.")
    angular_steps = {}
    for axis in ("theta", "phi"):
        step = parameters.get(f"radiation_{axis}_step_deg", 15)
        if isinstance(step, bool) or step not in (5, 10, 15, 30):
            raise ValueError("Radiation angular steps must be 5, 10, 15, or 30 degrees.")
        angular_steps[f"radiation_{axis}_step_deg"] = int(step)
    angular_count = (181 // angular_steps["radiation_theta_step_deg"] + 1) * (361 // angular_steps["radiation_phi_step_deg"] + 1) + 37
    if angular_count * points > 100_000:
        raise ValueError("Frequency and radiation grids exceed the 100000-sample budget.")
    if nearfield_enabled and grid_points ** 2 * points > 100_000:
        raise ValueError("Frequency and nearfield grids exceed the 100000-sample budget.")
    margin = parameters.get("air_margin_mm")
    if margin is not None:
        margin = number(margin, "absorbing air margin", low=5, high=200)
    nearfield_z = number(parameters.get("nearfield_z_mm", 1), "nearfield plane height", low=0.05, high=100)
    if nearfield_enabled and nearfield_z >= (margin if margin is not None else min(max(299792458 / fstop / 4 * 1000, 20), 100)):
        raise ValueError("Nearfield plane must be inside the absorbing air margin.")
    case = {"contract": "spike/emerge-board-case/v1", "bounds_mm": bounds,
            "dielectric_thickness_mm": thickness, "epsilon_r": epsilon,
            "copper_layers": copper_layers, "dielectric_layers": dielectric_layers,
            "geometry_backend": geometry_backend,
            "loss_tangent_omitted": 0 if include_loss else loss, "include_dielectric_loss": include_loss,
            "reference_impedance_ohm": impedance, "parallel": parallel, "n_workers": workers,
            "sparse_solver": sparse_solver,
            "field_excited_port": excited_port,
            "air_margin_mm": margin, **angular_steps,
            "radiation_cut_phi_deg": number(parameters.get("radiation_cut_phi_deg", 0), "radiation cut phi", low=0, high=360),
            "nearfield_enabled": nearfield_enabled, "nearfield_z_mm": nearfield_z,
            "nearfield_grid_points": grid_points, "polygons": polygons, "ports": ports,
            "frequency_start_hz": fstart, "frequency_stop_hz": fstop,
            "frequency_points": points, "mesh_resolution_mm": resolution,
            "planar_cell_estimate": math.ceil(planar_estimate),
            "layered_cell_estimate": math.ceil(planar_estimate * len(dielectric_layers)),
            "shorting_vias": shorting_vias,
            "attributed_graphic_polygon_ids": attributed_graphics,
            "idealized_reference_plane_ids": idealized_planes,
            "fragment_copper": fragment_copper,
            "modeled_nets": [*signal_nets, return_net], "port_mapping": port_mapping,
            "geometry_status": "approximate_rectangular_surface_pec_with_dielectric_surroundings" if surroundings else "approximate_rectangular_surface_pec"}
    if surroundings:
        case["surrounding_geometry"] = surroundings
    return case
