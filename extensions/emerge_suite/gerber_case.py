# SPDX-License-Identifier: Apache-2.0
"""Compile retained native Gerber metadata into an executable EMerge case."""

from __future__ import annotations

import math

from extensions.emerge_suite.board_adapter import admit_conductor_loss, _surroundings, number
from extensions.emerge_suite.gerber_source import normalize_gerber_source, source_digest


def _effective_stackup(design: dict, source: dict) -> tuple[list[dict], list[dict]]:
    stackup = design.get("stackup")
    if not isinstance(stackup, list):
        raise ValueError("Native Gerber execution requires the current SPIKE design stackup.")
    relevant = [row for row in stackup if isinstance(row, dict) and
                (str(row.get("name", "")).endswith(".Cu") or
                 str(row.get("type", "")).lower() in {"core", "prepreg", "dielectric"})]
    expected_count = len(source["layers"]) * 2 - 1
    if len(relevant) != expected_count:
        raise ValueError("Current Gerber stackup must alternate every retained copper layer and dielectric gap.")
    copper_layers = []
    dielectric_layers = []
    depth = 0.0
    for index, row in enumerate(relevant):
        if index % 2 == 0:
            expected_name = source["layers"][index // 2]["name"]
            if row.get("name") != expected_name:
                raise ValueError("Current stackup copper order does not match retained Gerber layer files.")
            copper_layers.append({"name": expected_name, "z_mm": -depth})
            continue
        thickness = number(row.get("thickness_mm", row.get("thickness")),
                           "dielectric thickness", low=.01, high=10)
        epsilon_r = number(row.get("epsilon_r", row.get("relative_permittivity")),
                           "relative permittivity", low=1.01, high=30)
        loss_tangent = number(row.get("loss_tangent", 0), "loss tangent", low=0, high=1)
        dielectric_layers.append({"name": str(row.get("name") or f"Dielectric {(index + 1) // 2}"),
                                  "thickness_mm": thickness, "epsilon_r": epsilon_r,
                                  "loss_tangent": loss_tangent, "z_top_mm": -depth,
                                  "z_bottom_mm": -(depth + thickness)})
        depth += thickness
    if depth > 10:
        raise ValueError("Total dielectric thickness exceeds 10 mm.")
    return copper_layers, dielectric_layers


def compile_gerber(design: dict, parameters: dict) -> dict:
    if not isinstance(design, dict) or design.get("contract") != "spike/v1":
        raise ValueError("Native Gerber execution requires an admitted SpiDeR design.")
    if design.get("source_format") != "emerge-gerber":
        raise ValueError("Native Gerber execution requires design.source_format emerge-gerber.")
    if not isinstance(parameters, dict):
        raise ValueError("EMerge Gerber setup parameters must be an object.")
    admit_conductor_loss(parameters)
    if parameters.get("geometry_source") not in {None, "gerber"}:
        raise ValueError("geometry_source does not match the imported Gerber design.")
    metadata = design.get("metadata")
    package = normalize_gerber_source(metadata.get("emerge_gerber_source") if isinstance(metadata, dict) else None)
    digest = source_digest(package)
    if metadata.get("emerge_gerber_source_sha256") != digest:
        raise ValueError("Retained Gerber source digest does not match its content.")
    if package["drills"]:
        raise ValueError("Retained Excellon drills are not yet supported by the native Gerber runner.")

    fstart = number(parameters.get("frequency_start_hz"), "start frequency", low=1e8, high=1e11)
    fstop = number(parameters.get("frequency_stop_hz"), "stop frequency", low=1e8, high=1e11)
    if fstop <= fstart:
        raise ValueError("Stop frequency must exceed start frequency.")
    points = parameters.get("frequency_points")
    if isinstance(points, bool) or not isinstance(points, int) or not 2 <= points <= 64:
        raise ValueError("Frequency points must be an integer from 2 to 64.")
    mesh_resolution = number(parameters.get("mesh_resolution_mm"), "mesh resolution", low=.05, high=10)
    bounds = package["bounds_mm"]
    surroundings = _surroundings(parameters.get("surrounding_geometry"), bounds)
    planar_estimate = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) / mesh_resolution**2
    if planar_estimate * len(package["dielectrics"]) > 200_000:
        raise ValueError("Gerber bounds and mesh resolution exceed the 200000-cell planar preflight budget.")
    include_loss = parameters.get("include_dielectric_loss", False)
    parallel = parameters.get("parallel", False)
    nearfield_enabled = parameters.get("nearfield_enabled", False)
    if any(not isinstance(value, bool) for value in (include_loss, parallel, nearfield_enabled)):
        raise ValueError("Dielectric loss, parallel, and nearfield controls must be booleans.")
    sparse_solver = parameters.get("sparse_solver", "auto")
    if sparse_solver not in {"auto", "superlu"}:
        raise ValueError("Sparse solver must be auto or superlu.")
    workers = parameters.get("n_workers", 2)
    grid_points = parameters.get("nearfield_grid_points", 11)
    for value, label, minimum, maximum in ((workers, "n_workers", 1, 8),
                                           (grid_points, "nearfield_grid_points", 3, 41)):
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"{label} is outside its bounded integer range.")
    if nearfield_enabled and grid_points * grid_points * points > 100_000:
        raise ValueError("Frequency and near-field grids exceed the 100000-sample budget.")
    angular_steps = {}
    for axis in ("theta", "phi"):
        step = parameters.get(f"radiation_{axis}_step_deg", 15)
        if isinstance(step, bool) or step not in (5, 10, 15, 30):
            raise ValueError("Radiation angular steps must be 5, 10, 15, or 30 degrees.")
        angular_steps[f"radiation_{axis}_step_deg"] = int(step)
    angular_count = ((181 // angular_steps["radiation_theta_step_deg"] + 1) *
                     (361 // angular_steps["radiation_phi_step_deg"] + 1) + 37)
    if angular_count * points > 100_000:
        raise ValueError("Frequency and radiation grids exceed the 100000-sample budget.")
    margin = parameters.get("air_margin_mm")
    if margin is not None:
        margin = number(margin, "absorbing air margin", low=5, high=200)
    nearfield_z = number(parameters.get("nearfield_z_mm", 1), "nearfield plane height",
                         low=.05, high=100)
    default_margin = min(max(299792458 / fstop / 4 * 1000, 20), 100)
    if nearfield_enabled and nearfield_z >= (margin if margin is not None else default_margin):
        raise ValueError("Nearfield plane must be inside the absorbing air margin.")
    impedance = number(parameters.get("reference_impedance_ohm", 50),
                       "reference impedance", low=1, high=1000)
    excited = parameters.get("field_excited_port", 1)
    if isinstance(excited, bool) or not isinstance(excited, int) or not 1 <= excited <= len(package["ports"]):
        raise ValueError("Field excited port must identify an admitted Gerber port.")

    copper_layers, dielectric_layers = _effective_stackup(design, package)
    depth = sum(row["thickness_mm"] for row in dielectric_layers)
    z_by_layer = {row["name"]: row["z_mm"] for row in copper_layers}
    ports = []
    port_mapping = []
    for row in package["ports"]:
        z_signal = z_by_layer[row["signal_layer"]]
        z_return = z_by_layer[row["return_layer"]]
        port = {**row, "z_bottom_mm": z_return, "height_mm": z_signal - z_return,
                "reference_impedance_ohm": impedance}
        ports.append(port)
        port_mapping.append({"port": row["id"], "source_port_id": row["id"],
                             "signal_net": "GerberRF", "return_net": "GerberReturn",
                             "signal_layer": row["signal_layer"],
                             "return_layer": row["return_layer"],
                             "mapping_status": "manual_unverified_source_annotation"})
    loss = max((row["loss_tangent"] for row in dielectric_layers), default=0.0)
    case = {
        "contract": "spike/emerge-board-case/v1", "source_format": "emerge-gerber",
        "source_design_id": design.get("design_id"), "bounds_mm": bounds,
        "dielectric_thickness_mm": depth,
        "epsilon_r": dielectric_layers[0]["epsilon_r"],
        "copper_layers": copper_layers, "dielectric_layers": dielectric_layers,
        "geometry_backend": "emerge-gerber", "native_gerber_source_sha256": digest,
        "native_gerber_layers": package["layers"], "native_gerber_drills": package["drills"],
        "gerber_resolution_mm": package["resolution_mm"], "polygons": [],
        "loss_tangent_omitted": 0 if include_loss else loss,
        "include_dielectric_loss": include_loss,
        "reference_impedance_ohm": impedance, "parallel": parallel,
        "n_workers": workers, "sparse_solver": sparse_solver,
        "field_excited_port": excited, "air_margin_mm": margin, **angular_steps,
        "radiation_cut_phi_deg": number(parameters.get("radiation_cut_phi_deg", 0),
                                         "radiation cut phi", low=0, high=360),
        "nearfield_enabled": nearfield_enabled, "nearfield_z_mm": nearfield_z,
        "nearfield_grid_points": grid_points, "ports": ports,
        "frequency_start_hz": fstart, "frequency_stop_hz": fstop,
        "frequency_points": points, "mesh_resolution_mm": mesh_resolution,
        "planar_cell_estimate": math.ceil(planar_estimate),
        "layered_cell_estimate": math.ceil(planar_estimate * len(dielectric_layers)),
        "shorting_vias": [], "fragment_copper": False,
        "modeled_nets": ["GerberRF", "GerberReturn"], "port_mapping": port_mapping,
        "geometry_status": ("native_gerber_surface_pec_with_dielectric_surroundings_unvalidated"
                            if surroundings else "native_gerber_surface_pec_unvalidated"),
        "material_assignment_source": "current_spiDeR_stackup",
        "source_assumptions": [
            "Gerber artwork has no source net connectivity.",
            "Manual port coordinates are not verified against source pads.",
            "Copper is modeled as zero-thickness PEC surfaces.",
            "Declared rectangular bounds define the dielectric board extent.",
        ],
    }
    if surroundings:
        case["surrounding_geometry"] = surroundings
        case["source_assumptions"].append(
            "Surrounding dielectrics are explicit ideal boxes with constant relative permittivity.")
    return case
