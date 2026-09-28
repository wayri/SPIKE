# SPDX-License-Identifier: Apache-2.0
"""Approximate steady 3D board heat flow on a layered finite-volume grid.

Each physical stackup row owns one z cell. In-plane copper is an area-fraction
effective conductivity; vertical interfaces use two half-cell resistances in
series. This is a structured volume network, not a tetrahedral mesh or a 3D
package model. Lengths enter in mm and are converted to SI before assembly.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import replace
from typing import Any

import numpy as np
from scipy.sparse import diags, lil_matrix
from scipy.sparse.linalg import splu, spsolve

from .board_thermal import CONTRACT, MAX_CELLS, MAX_COMPONENTS, _number, _pad_contacts, _point
from .contracts import DesignIR
from .thermal_copper_geometry import rasterize_copper


def _stackup(design: DesignIR, thickness: float) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(design.stackup, list) or len(design.stackup) < 3:
        raise ValueError("Layered thermal model needs an explicit copper/dielectric stackup.")
    rows: list[dict[str, Any]] = []
    names: list[str] = []
    for index, raw in enumerate(design.stackup):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Stackup row {index} must be an object.")
        name = str(raw.get("name", "")).strip()
        kind = str(raw.get("type", "")).lower()
        if kind in {"top silk screen", "bottom silk screen", "top solder paste", "bottom solder paste",
                    "top solder mask", "bottom solder mask"} or name.endswith((".SilkS", ".Paste", ".Mask")):
            continue
        copper = kind == "copper" or name.endswith(".Cu")
        if not name or (kind == "copper" and not name.endswith(".Cu")) or (not copper and kind not in {"", "core", "prepreg", "dielectric"}):
            raise ValueError(f"Stackup row {index} has no supported layer name.")
        depth = _number(raw.get("thickness", raw.get("thickness_mm")), f"stackup {name} thickness", positive=True)
        if copper:
            if name in names:
                raise ValueError(f"Duplicate copper layer {name} in stackup.")
            names.append(name)
        rows.append({"name": name, "thickness_mm": depth, "copper": copper})
    if len(rows) < 3 or not rows[0]["copper"] or not rows[-1]["copper"] or len(names) < 2:
        raise ValueError("Stackup must start and end with distinct copper layers.")
    if any(rows[i]["copper"] == rows[i + 1]["copper"] for i in range(len(rows) - 1)):
        raise ValueError("Stackup copper and dielectric rows must alternate.")
    if abs(sum(row["thickness_mm"] for row in rows) - thickness) > 0.05 * thickness:
        raise ValueError("Physical stackup thickness differs from board thickness by more than 5%.")
    return rows, names


def _layer_span(raw: Any, names: list[str], label: str) -> tuple[int, int]:
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError(f"{label} needs two copper span endpoints.")
    try:
        a, b = names.index(str(raw[0])), names.index(str(raw[1]))
    except ValueError as exc:
        raise ValueError(f"{label} references an unknown copper layer.") from exc
    if a == b:
        raise ValueError(f"{label} span endpoints must differ.")
    return min(a, b), max(a, b)


def _barrel_paths(design: DesignIR, names: list[str], plating: float) -> list[tuple[float, float, int, int, float]]:
    paths: list[tuple[float, float, int, int, float]] = []
    for i, via in enumerate(design.vias):
        if not isinstance(via, Mapping):
            raise ValueError(f"Via {i} must be an object.")
        lo, hi = _layer_span(via.get("layers"), names, f"via {i}")
        x, y = _point(via, f"via {i}")
        drill = _number(via.get("drill"), f"via {i} drill", positive=True)
        land = _number(via.get("size", via.get("diameter")), f"via {i} land", positive=True)
        if land <= drill or 2 * plating >= drill:
            raise ValueError(f"Via {i} has incompatible drill, land, or plating thickness.")
        # Imported drill is the finished bore diameter; plating lies outside it.
        area_mm2 = math.pi * (drill * plating + plating * plating)
        paths.append((x, y, lo, hi, area_mm2))
    for i, pad in enumerate(design.pads):
        if not isinstance(pad, Mapping):
            raise ValueError(f"Pad {i} must be an object.")
        kind = str(pad.get("pad_kind") or pad.get("type") or "").lower()
        if kind in {"np_thru_hole", "unplated", "npth", "smd", "connect"}:
            continue
        drilled = pad.get("drill_size", pad.get("drill"))
        if kind not in {"", "thru_hole", "through_hole", "pth"}:
            raise ValueError(f"Pad {i} has unsupported plating type {kind}.")
        if kind == "" and (not drilled or drilled == (0, 0)):
            continue
        layers = pad.get("layers")
        if isinstance(layers, (list, tuple)) and ("*.Cu" in layers or "F&B.Cu" in layers):
            lo, hi = 0, len(names) - 1
        else:
            lo, hi = _layer_span(layers, names, f"pad {i}")
        drill_raw = pad.get("drill_size", pad.get("drill"))
        if isinstance(drill_raw, (list, tuple)):
            if len(drill_raw) < 2:
                raise ValueError(f"Pad {i} has invalid drill dimensions.")
            major = max(_number(drill_raw[0], "pad drill", positive=True), _number(drill_raw[1], "pad drill", positive=True))
            minor = min(_number(drill_raw[0], "pad drill", positive=True), _number(drill_raw[1], "pad drill", positive=True))
        else:
            major = minor = _number(drill_raw, f"pad {i} drill", positive=True)
        if 2 * plating >= minor:
            raise ValueError(f"Pad {i} drill is too small for plating thickness.")
        land_size = pad.get("size")
        if not isinstance(land_size, (list, tuple)) or len(land_size) < 2 or min(_number(v, "pad land", positive=True) for v in land_size[:2]) <= minor:
            raise ValueError(f"Pad {i} has no valid copper land around its bore.")
        # Oval drill is treated as a rounded slot; offset plating shell area.
        perimeter = 2 * (major - minor) + math.pi * minor
        barrel_area = perimeter * plating + math.pi * plating * plating
        x, y = _point(pad, f"pad {i}")
        paths.append((x, y, lo, hi, barrel_area))
    return paths


def solve_layered_board_thermal(design: DesignIR, request: Mapping[str, Any]) -> dict[str, Any]:
    """Solve a bounded layered board; caller converts input errors to blocked results."""
    board = request.get("board")
    parts = request.get("components")
    if not isinstance(board, Mapping) or not isinstance(parts, list) or not 1 <= len(parts) <= MAX_COMPONENTS:
        raise ValueError("Provide board properties and 1..256 powered component rows.")
    bounds = design.metadata.get("board_bounds_mm") if isinstance(design.metadata, Mapping) else None
    if design.units != "mm" or not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        raise ValueError("Layered board needs millimetre units and finite board bounds.")
    xmin, ymin, xmax, ymax = (_number(v, "board bound") for v in bounds)
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("Board bounds must have positive width and height.")
    thickness = _number(board.get("thickness_mm"), "board thickness_mm", positive=True)
    rows, names = _stackup(design, thickness)
    step = _number(board.get("grid_step_mm"), "board grid_step_mm", positive=True)
    nx, ny = math.ceil((xmax - xmin) / step), math.ceil((ymax - ymin) / step)
    cells = nx * ny
    if cells > MAX_CELLS or cells * len(rows) > 131072:
        raise ValueError("Layered grid exceeds the bounded cell limit; increase grid_step_mm.")
    dx, dy = (xmax - xmin) / nx, (ymax - ymin) / ny
    area_m2 = dx * dy * 1e-6
    ambient = _number(request.get("ambient_temperature_c"), "ambient_temperature_c")
    if ambient < -273.15:
        raise ValueError("Ambient temperature is below absolute zero.")
    kd = _number(board.get("dielectric_conductivity_w_mk"), "dielectric conductivity", positive=True)
    kc = _number(board.get("copper_conductivity_w_mk"), "copper conductivity", positive=True)
    htop = _number(board.get("convection_top_w_m2k"), "top convection")
    hbottom = _number(board.get("convection_bottom_w_m2k"), "bottom convection")
    if htop < 0 or hbottom < 0 or htop + hbottom <= 0:
        raise ValueError("At least one nonnegative convection coefficient must be positive.")
    include_copper = board.get("include_copper", True)
    include_vias = board.get("include_vias", True)
    toggles = {key: board.get(key, True) for key in ("include_tracks", "include_pads", "include_zones")}
    if any(not isinstance(v, bool) for v in (include_copper, include_vias, *toggles.values())):
        raise ValueError("Geometry toggles must be boolean.")
    sigma = _number(board.get("fuzzy_sigma_mm", 0), "fuzzy_sigma_mm")
    if sigma < 0:
        raise ValueError("fuzzy_sigma_mm cannot be negative.")
    if include_copper:
        coverage, diagnostics = rasterize_copper(design, (xmin, ymin, xmax, ymax), (nx, ny), (dx, dy), names,
            fuzzy_sigma_mm=sigma, include_tracks=toggles["include_tracks"],
            include_pads=toggles["include_pads"], include_zones=toggles["include_zones"],
            include_via_lands=include_vias)
    else:
        coverage = {name: np.zeros((ny, nx)) for name in names}
        diagnostics = []
    raw_heatsinks = request.get("virtual_heatsinks", [])
    if not isinstance(raw_heatsinks, list) or len(raw_heatsinks) > 16:
        raise ValueError("Provide at most 16 virtual board heatsinks.")
    heatsinks: list[dict[str, Any]] = []
    sink_ids: set[str] = set()
    for index, raw in enumerate(raw_heatsinks):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Virtual heatsink {index + 1} must be an object.")
        identifier = str(raw.get("id", "")).strip()
        if not identifier or identifier in sink_ids:
            raise ValueError("Virtual heatsinks need unique nonempty IDs.")
        sink_ids.add(identifier)
        face = raw.get("face")
        if face not in ("top", "bottom"):
            raise ValueError(f"Virtual heatsink {identifier} face must be top or bottom.")
        x = _number(raw.get("x_mm"), f"{identifier} x_mm")
        y = _number(raw.get("y_mm"), f"{identifier} y_mm")
        width = _number(raw.get("width_mm"), f"{identifier} width_mm", positive=True)
        height = _number(raw.get("height_mm"), f"{identifier} height_mm", positive=True)
        interface = _number(raw.get("interface_resistance_k_w"), f"{identifier} interface resistance")
        ambient_resistance = _number(raw.get("sink_to_ambient_k_w"), f"{identifier} sink-to-ambient resistance", positive=True)
        if interface < 0 or x - width / 2 < xmin or x + width / 2 > xmax or y - height / 2 < ymin or y + height / 2 > ymax:
            raise ValueError(f"Virtual heatsink {identifier} needs nonnegative interface resistance and a footprint inside board bounds.")
        heatsinks.append({"id": identifier, "face": face, "x_mm": x, "y_mm": y,
                          "width_mm": width, "height_mm": height,
                          "interface_resistance_k_w": interface,
                          "sink_to_ambient_k_w": ambient_resistance})
    n = cells * len(rows)
    pad_parts = sum(1 for item in parts if isinstance(item, Mapping) and item.get("contact_mode") == "pads")
    node_count = n + pad_parts + len(heatsinks)
    matrix = lil_matrix((node_count, node_count), dtype=float)
    rhs = np.zeros(node_count)
    sink = np.zeros(n)
    depth_m = np.array([row["thickness_mm"] * 1e-3 for row in rows])
    k = np.empty((len(rows), ny, nx))
    copper_index = {name: i for i, name in enumerate(names)}
    for z, row in enumerate(rows):
        k[z] = kd + (kc - kd) * coverage[row["name"]] if row["copper"] and include_copper else kd
    if np.any(k <= 0) or not np.all(np.isfinite(k)):
        raise ValueError("Effective thermal conductivity is invalid.")

    def edge(a: int, b: int, g: float) -> None:
        if not math.isfinite(g) or g <= 0:
            raise ValueError("Thermal edge conductance is invalid.")
        matrix[a, a] += g
        matrix[b, b] += g
        matrix[a, b] -= g
        matrix[b, a] -= g

    for z in range(len(rows)):
        for iy in range(ny):
            for ix in range(nx):
                a = z * cells + iy * nx + ix
                ka = k[z, iy, ix]
                if ix + 1 < nx:
                    kb = k[z, iy, ix + 1]
                    edge(a, a + 1, 2 * ka * kb / (ka + kb) * depth_m[z] * dy / dx)
                if iy + 1 < ny:
                    kb = k[z, iy + 1, ix]
                    edge(a, a + nx, 2 * ka * kb / (ka + kb) * depth_m[z] * dx / dy)
                if z + 1 < len(rows):
                    kb = k[z + 1, iy, ix]
                    edge(a, a + cells, area_m2 / (depth_m[z] / (2 * ka) + depth_m[z + 1] / (2 * kb)))
                if z == 0 and htop > 0:
                    sink[a] = area_m2 / (depth_m[z] / (2 * ka) + 1 / htop)
                if z == len(rows) - 1 and hbottom > 0:
                    sink[a] = area_m2 / (depth_m[z] / (2 * ka) + 1 / hbottom)
    for a in range(n):
        matrix[a, a] += sink[a]
        rhs[a] += sink[a] * ambient

    if include_vias:
        plating = _number(board.get("via_plating_thickness_mm"), "via plating thickness", positive=True)
        for x, y, lo, hi, barrel_area in _barrel_paths(design, names, plating):
            if not xmin <= x <= xmax or not ymin <= y <= ymax:
                raise ValueError("Plated barrel is outside board bounds.")
            cell = min(ny - 1, int((y - ymin) / dy)) * nx + min(nx - 1, int((x - xmin) / dx))
            za = next(i for i, row in enumerate(rows) if row["name"] == names[lo])
            zb = next(i for i, row in enumerate(rows) if row["name"] == names[hi])
            for z in range(za, zb):
                distance = (depth_m[z] + depth_m[z + 1]) / 2
                edge(z * cells + cell, (z + 1) * cells + cell, kc * barrel_area * 1e-6 / distance)

    for sink_index, item in enumerate(heatsinks):
        node = n + pad_parts + sink_index
        z = 0 if item["face"] == "top" else len(rows) - 1
        x0, x1 = item["x_mm"] - item["width_mm"] / 2, item["x_mm"] + item["width_mm"] / 2
        y0, y1 = item["y_mm"] - item["height_mm"] / 2, item["y_mm"] + item["height_mm"] / 2
        contacts = []
        for iy in range(ny):
            overlap_y = max(0.0, min(ymin + (iy + 1) * dy, y1) - max(ymin + iy * dy, y0))
            if overlap_y == 0:
                continue
            for ix in range(nx):
                overlap_x = max(0.0, min(xmin + (ix + 1) * dx, x1) - max(xmin + ix * dx, x0))
                area = overlap_x * overlap_y
                if area == 0:
                    continue
                weight = area / (item["width_mm"] * item["height_mm"])
                half_cell_r = depth_m[z] / (2 * k[z, iy, ix] * area * 1e-6)
                conductance = 1 / (item["interface_resistance_k_w"] / weight + half_cell_r)
                cell_node = z * cells + iy * nx + ix
                edge(cell_node, node, conductance)
                contacts.append((cell_node, weight))
        if not contacts or abs(sum(weight for _, weight in contacts) - 1) > 1e-9:
            raise ValueError(f"Virtual heatsink {item['id']} footprint was not conserved on the board grid.")
        ambient_g = 1 / item["sink_to_ambient_k_w"]
        matrix[node, node] += ambient_g
        rhs[node] += ambient_g * ambient
        item["_node"] = node
        item["_contacts"] = contacts

    available = {str(item.get("reference") or item.get("ref") or ""): item
                 for item in design.components if isinstance(item, Mapping)}
    admitted: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_power = 0.0
    next_case = n
    for raw in parts:
        if not isinstance(raw, Mapping):
            raise ValueError("Each component assignment must be an object.")
        ref = str(raw.get("component_ref", "")).strip()
        if not ref or ref.casefold() in seen or ref not in available:
            raise ValueError(f"Thermal component {ref!r} is duplicated or absent from the imported board.")
        seen.add(ref.casefold())
        x, y = _point(available[ref], ref)
        if not xmin <= x <= xmax or not ymin <= y <= ymax:
            raise ValueError(f"{ref} lies outside board bounds.")
        power = _number(raw.get("power_w"), f"{ref} power_w")
        rjc = _number(raw.get("r_junction_case_k_w"), f"{ref} r_junction_case_k_w", positive=True)
        rcb = _number(raw.get("r_case_board_k_w"), f"{ref} r_case_board_k_w", positive=True)
        if power < 0:
            raise ValueError(f"{ref} power_w cannot be negative.")
        ix, iy = min(nx - 1, int((x - xmin) / dx)), min(ny - 1, int((y - ymin) / dy))
        mode = raw.get("contact_mode", "square")
        item = {"component_ref": ref, "position_mm": [x, y], "cell": [ix, iy], "power_w": power,
                "contact_mode": mode, "r_junction_case_k_w": rjc, "r_case_board_k_w": rcb}
        if mode == "pads":
            if not toggles["include_pads"]:
                raise ValueError("Pad contact mode requires include_pads.")
            contacts: list[dict[str, Any]] = []
            for face, z in ((names[0], 0), (names[-1], len(rows) - 1)):
                face_pads = []
                for pad in design.pads:
                    if not isinstance(pad, Mapping):
                        continue
                    layers = pad.get("layers", [pad.get("layer")])
                    if isinstance(layers, str):
                        layers = [layers]
                    if not isinstance(layers, (list, tuple)):
                        raise ValueError(f"{ref} pad has invalid layer membership.")
                    if face in layers or "*.Cu" in layers or "F&B.Cu" in layers:
                        face_pads.append(pad)
                for contact in _pad_contacts(replace(design, pads=face_pads), ref, (xmin, ymin, xmax, ymax),
                                             (nx, ny), (dx, dy)):
                    contact["layer"] = face
                    contact["_z"] = z
                    contacts.append(contact)
            if not contacts:
                raise ValueError(f"{ref} has no admitted surface copper pad land.")
            area = sum(c["area_mm2"] for c in contacts)
            case = next_case
            next_case += 1
            conductances = []
            rhs[case] = power
            for contact in contacts:
                g = contact["area_mm2"] / (area * rcb)
                conductances.append(g)
                weights = [(contact["_z"] * cells + j, weight) for j, weight in contact["_weights"]]
                matrix[case, case] += g
                for j, wj in weights:
                    matrix[j, case] -= g * wj
                    matrix[case, j] -= g * wj
                    for q, wq in weights:
                        matrix[j, q] += g * wj * wq
            item.update(pad_count=len(contacts), _case=case, _contacts=contacts, _conductances=conductances)
        elif mode == "square":
            size = _number(raw.get("contact_size_mm"), f"{ref} contact_size_mm", positive=True)
            half = size / 2
            if x - half < xmin or x + half > xmax or y - half < ymin or y + half > ymax:
                raise ValueError(f"{ref} contact area extends outside board bounds.")
            weights = []
            for cy in range(ny):
                oy = max(0.0, min(ymin + (cy + 1) * dy, y + half) - max(ymin + cy * dy, y - half))
                for cx in range(nx):
                    ox = max(0.0, min(xmin + (cx + 1) * dx, x + half) - max(xmin + cx * dx, x - half))
                    if ox * oy > 0:
                        weights.append((cy * nx + cx, ox * oy / (size * size)))
            if not weights or abs(sum(w for _, w in weights) - 1) > 1e-10:
                raise ValueError(f"{ref} square contact area was not conserved.")
            for j, weight in weights:
                rhs[j] += power * weight
            item.update(contact_size_mm=size, _weights=weights)
        else:
            raise ValueError(f"{ref} contact_mode must be pads or square.")
        admitted.append(item)
        total_power += power
    if not math.isfinite(total_power):
        raise ValueError("Total power exceeds finite numerical range.")
    coefficients = matrix.tocsc()
    values = np.asarray(spsolve(coefficients, rhs), dtype=float)
    if values.shape != (node_count,) or not np.all(np.isfinite(values)) or np.min(values) < -273.15:
        raise ValueError("Layered thermal system returned invalid temperatures.")
    relative = float(np.linalg.norm(coefficients @ values - rhs) / max(np.linalg.norm(rhs), 1e-30))
    convection_outward = float(np.dot(sink, values[:n] - ambient))
    heatsink_outward = sum((float(values[item["_node"]]) - ambient) / item["sink_to_ambient_k_w"] for item in heatsinks)
    outward = convection_outward + heatsink_outward
    energy_error = outward - total_power
    if relative > 1e-9 or abs(energy_error) > 1e-8 * max(1.0, total_power):
        raise ValueError("Layered thermal residual or energy balance did not pass.")
    transient_frames: list[dict[str, Any]] = []
    transient_summary: dict[str, float] = {}
    transient_input = request.get("transient")
    if transient_input is not None:
        if not isinstance(transient_input, Mapping):
            raise ValueError("Transient board controls must be an object.")
        end_time = _number(transient_input.get("end_time_s"), "transient end_time_s", positive=True)
        dt = _number(transient_input.get("time_step_s"), "transient time_step_s", positive=True)
        ratio = end_time / dt
        if not math.isfinite(ratio) or abs(ratio - round(ratio)) > 1e-9 * max(1.0, ratio):
            raise ValueError("Transient end_time_s must be an integer multiple of time_step_s.")
        steps = round(ratio)
        stride = transient_input.get("output_stride", 1)
        if type(stride) is not int or stride < 1 or steps < 1 or steps > 240:
            raise ValueError("Transient run needs 1..240 steps and a positive integer output_stride.")
        output_count = 1 + (steps + stride - 1) // stride
        if output_count > 24 or n * output_count > 500_000:
            raise ValueError("Transient output exceeds 24 frames or 500,000 board temperature values; increase output_stride or grid step.")
        copper_capacity = _number(transient_input.get("copper_volumetric_heat_capacity_j_m3k"),
                                  "copper volumetric heat capacity", positive=True)
        dielectric_capacity = _number(transient_input.get("dielectric_volumetric_heat_capacity_j_m3k"),
                                      "dielectric volumetric heat capacity", positive=True)
        capacity = np.zeros(node_count)
        for z, row in enumerate(rows):
            fraction = coverage[row["name"]] if row["copper"] and include_copper else 0.0
            volumetric = dielectric_capacity + (copper_capacity - dielectric_capacity) * fraction
            capacity[z * cells:(z + 1) * cells] = (area_m2 * depth_m[z] * volumetric).ravel() if isinstance(volumetric, np.ndarray) else area_m2 * depth_m[z] * volumetric
        inertia = capacity / dt
        factor = splu(coefficients + diags(inertia, format="csc"))
        prior = np.full(node_count, ambient)
        max_balance_error = 0.0
        max_step_residual = 0.0
        def frame(time_s: float, temperatures: np.ndarray, storage_rate_w: float, balance_error_w: float) -> dict[str, Any]:
            return {"time_s": time_s,
                    "layer_temperatures_c": [temperatures[z * cells:(z + 1) * cells].tolist() for z in range(len(rows))],
                    "maximum_board_temperature_c": float(np.max(temperatures[:n])),
                    "storage_rate_w": storage_rate_w,
                    "energy_balance_error_w": balance_error_w}
        transient_frames.append(frame(0.0, prior, 0.0, 0.0))
        for step_index in range(1, steps + 1):
            transient_rhs = rhs + inertia * prior
            current = np.asarray(factor.solve(transient_rhs), dtype=float)
            if current.shape != (node_count,) or not np.all(np.isfinite(current)) or np.min(current) < -273.15:
                raise ValueError("Transient board solve returned invalid temperatures.")
            step_residual = float(np.linalg.norm((coefficients @ current) + inertia * (current - prior) - rhs) / max(np.linalg.norm(transient_rhs), 1e-30))
            max_step_residual = max(max_step_residual, step_residual)
            outward_step = float(np.dot(sink, current[:n] - ambient)) + sum(
                (float(current[item["_node"]]) - ambient) / item["sink_to_ambient_k_w"] for item in heatsinks)
            storage_rate = float(np.dot(capacity, (current - prior) / dt))
            balance_error = total_power - outward_step - storage_rate
            max_balance_error = max(max_balance_error, abs(balance_error))
            if step_index % stride == 0 or step_index == steps:
                transient_frames.append(frame(step_index * dt, current, storage_rate, balance_error))
            prior = current
        if max_step_residual > 1e-9 or max_balance_error > 1e-8 * max(1.0, total_power):
            raise ValueError("Transient board residual or energy balance did not pass.")
        transient_summary = {"transient_peak_board_temperature_c": max(item["maximum_board_temperature_c"] for item in transient_frames),
                             "transient_final_stored_energy_j": float(np.dot(capacity, prior[:node_count] - ambient)),
                             "max_transient_energy_balance_error_w": max_balance_error,
                             "max_transient_linear_relative_residual": max_step_residual}
    for item in heatsinks:
        node = item.pop("_node")
        contacts = item.pop("_contacts")
        item["temperature_c"] = float(values[node])
        item["board_contact_temperature_c"] = float(sum(values[index] * weight for index, weight in contacts))
        item["heat_flow_w"] = (item["temperature_c"] - ambient) / item["sink_to_ambient_k_w"]
    for item in admitted:
        if item["contact_mode"] == "pads":
            contacts = item.pop("_contacts")
            case_temp = float(values[item.pop("_case")])
            for contact, g in zip(contacts, item.pop("_conductances")):
                z = contact.pop("_z")
                contact["board_temperature_c"] = float(sum(values[z * cells + j] * w for j, w in contact.pop("_weights")))
                contact["heat_w"] = g * (case_temp - contact["board_temperature_c"])
            if abs(sum(c["heat_w"] for c in contacts) - item["power_w"]) > 1e-8 * max(1.0, item["power_w"]):
                raise ValueError("Pad heat flow did not conserve component power.")
            item["pad_contacts"] = contacts
            board_temp = sum(c["board_temperature_c"] * c["area_mm2"] for c in contacts) / sum(c["area_mm2"] for c in contacts)
        else:
            board_temp = float(sum(values[j] * w for j, w in item.pop("_weights")))
            case_temp = board_temp + item["power_w"] * item["r_case_board_k_w"]
        item.update(board_temperature_c=board_temp, case_temperature_c=case_temp,
                    junction_temperature_c=case_temp + item["power_w"] * item["r_junction_case_k_w"])
    layers = []
    for z, row in enumerate(rows):
        layers.append({"name": row["name"], "thickness_mm": row["thickness_mm"],
                       "temperatures_c": values[z * cells:(z + 1) * cells].tolist(),
                       "copper_coverage": coverage[row["name"]].ravel().tolist() if row["copper"] and include_copper else [0.0] * cells})
    return {"contract": CONTRACT, "status": "completed", "model_status": "approximate",
            "grid": {"origin_mm": [xmin, ymin], "spacing_mm": [dx, dy], "shape": [nx, ny],
                     "temperatures_c": layers[0]["temperatures_c"], "order": "x-fast"},
            "layer_grids": layers, "components": admitted, "virtual_heatsinks": heatsinks,
            "transient": transient_frames,
            "summary": {"minimum_board_temperature_c": float(np.min(values[:n])),
                        "maximum_board_temperature_c": float(np.max(values[:n])),
                        "maximum_junction_temperature_c": max(c["junction_temperature_c"] for c in admitted),
                        "total_power_w": total_power, "outward_heat_w": outward,
                        "convection_outward_heat_w": convection_outward,
                        "heatsink_outward_heat_w": heatsink_outward,
                        "energy_balance_error_w": energy_error, "linear_relative_residual": relative,
                        **transient_summary},
            "provenance": {"solver_id": "spike.layered_board_thermal", "design_id": design.design_id,
                           "fuzzy_sigma_mm": sigma if include_copper else 0.0,
                           "board_model": "layered_axis_aligned_finite_volume",
                           "boundary_model": "adiabatic_edges_and_top_bottom_convection",
                           "component_model": "surface_pad_case_coupling_or_square_contact",
                           "heatsink_model": "isothermal_virtual_node_with_explicit_interface_and_sink_to_ambient_resistance",
                           "transient_model": "backward_euler_constant_power_volumetric_capacity" if transient_input is not None else "not_requested",
                           "production_qualified": False, "request": dict(request)},
            "issues": diagnostics + [{"code": "BOARD_THERMAL_LAYERED_APPROXIMATE", "severity": "warning",
                "message": "Structured layered board only: no tetrahedra, package volume, board cutouts, radiation, or calibrated package heat spreading."}]}


__all__ = ["solve_layered_board_thermal"]
