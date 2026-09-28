# SPDX-License-Identifier: Apache-2.0
"""Bounded board-plate thermal solve with explicit component heat paths.

The board is an axis-aligned, uniform effective sheet over imported board
bounds. It is deliberately approximate: no copper topology, holes, case/air
geometry, or package-internal field is inferred from the KiCad design.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

from .contracts import DesignIR
from .hybrid_mesh import _clip_polygon_to_rect, _pad_boundary_polygon, _polygon_area
from .thermal_copper_geometry import CopperGeometryError

CONTRACT = "spike/board-thermal-result/v1"
MAX_CELLS = 8192
MAX_COMPONENTS = 256


def _pad_contacts(design: DesignIR, ref: str, bounds: tuple[float, float, float, float],
                  shape: tuple[int, int], spacing: tuple[float, float]) -> list[dict[str, Any]]:
    """Rasterize imported copper lands; omit unplated holes and copper voids."""
    xmin, ymin, xmax, ymax = bounds
    nx, ny = shape
    dx, dy = spacing
    contacts: list[dict[str, Any]] = []
    for pad in design.pads:
        if not isinstance(pad, Mapping) or str(pad.get("component") or pad.get("ref") or "") != ref:
            continue
        kind = str(pad.get("pad_kind") or pad.get("type") or "").lower()
        layers = pad.get("layers") or [pad.get("layer", "")]
        if kind == "np_thru_hole" or not isinstance(layers, (list, tuple)) or not any(str(layer).endswith(".Cu") for layer in layers):
            continue
        polygon = _pad_boundary_polygon(dict(pad), curve_segments=64)
        if len(polygon) < 3 or _polygon_area(polygon) <= 0:
            raise ValueError(f"{ref} has a copper pad with unsupported or empty geometry.")
        center = _point(pad, f"{ref} pad")
        drill_raw = pad.get("drill_size")
        if isinstance(drill_raw, (list, tuple)) and len(drill_raw) >= 2:
            drill = [_number(drill_raw[0], "pad drill"), _number(drill_raw[1], "pad drill")]
        else:
            diameter = _number(pad.get("drill", 0), "pad drill")
            drill = [diameter, diameter]
        if min(drill) < 0:
            raise ValueError(f"{ref} has an invalid drill dimension.")
        hole: list[tuple[float, float]] = []
        if min(drill) > 0:
            if str(pad.get("drill_shape", "circle")).lower() not in {"circle", "oval"}:
                raise ValueError(f"{ref} has unsupported pad drill shape.")
            hole = [(center[0] + drill[0] * math.cos(2 * math.pi * i / 64) / 2,
                     center[1] + drill[1] * math.sin(2 * math.pi * i / 64) / 2)
                    for i in range(64)]
        px0, px1 = min(p[0] for p in polygon), max(p[0] for p in polygon)
        py0, py1 = min(p[1] for p in polygon), max(p[1] for p in polygon)
        if px0 < xmin - 1e-7 or px1 > xmax + 1e-7 or py0 < ymin - 1e-7 or py1 > ymax + 1e-7:
            raise ValueError(f"{ref} copper pad extends outside board bounds.")
        ix0, ix1 = max(0, int((px0 - xmin) / dx)), min(nx - 1, int((px1 - xmin) / dx))
        iy0, iy1 = max(0, int((py0 - ymin) / dy)), min(ny - 1, int((py1 - ymin) / dy))
        overlaps: list[tuple[int, float]] = []
        for iy in range(iy0, iy1 + 1):
            for ix in range(ix0, ix1 + 1):
                rect = (xmin + ix * dx, ymin + iy * dy, xmin + (ix + 1) * dx, ymin + (iy + 1) * dy)
                area = _polygon_area(_clip_polygon_to_rect(polygon, *rect))
                if hole:
                    area -= _polygon_area(_clip_polygon_to_rect(hole, *rect))
                if area > 1e-12:
                    overlaps.append((iy * nx + ix, area))
        area = sum(value for _, value in overlaps)
        if area <= 1e-12:
            continue
        contacts.append({"pad_name": str(pad.get("name", "")), "position_mm": list(center),
                         "area_mm2": area, "_weights": [(index, value / area) for index, value in overlaps]})
    return contacts


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number.")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be a finite number.") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'finite'}.")
    return result


def _point(component: Mapping[str, Any], ref: str) -> tuple[float, float]:
    raw = component.get("at", component.get("position_mm"))
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise ValueError(f"{ref} has no imported board position.")
    return _number(raw[0], f"{ref} x"), _number(raw[1], f"{ref} y")


def _solve(design: DesignIR, request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(request, Mapping):
        raise ValueError("Board thermal request must be an object.")
    raw_board = request.get("board")
    raw_parts = request.get("components")
    if not isinstance(raw_board, Mapping) or not isinstance(raw_parts, list) or not 1 <= len(raw_parts) <= MAX_COMPONENTS:
        raise ValueError("Provide board properties and 1..256 powered component rows.")
    model = raw_board.get("model", "plate")
    if model == "layered":
        from .layered_board_thermal import solve_layered_board_thermal
        return solve_layered_board_thermal(design, request)
    if request.get("virtual_heatsinks"):
        raise ValueError("Virtual board heatsinks require the layered model and a physical stackup.")
    if request.get("transient") is not None:
        raise ValueError("Spatial board transient requires the layered model and a physical stackup.")
    if model != "plate":
        raise ValueError("Board thermal model must be plate or layered.")
    bounds = design.metadata.get("board_bounds_mm") if isinstance(design.metadata, Mapping) else None
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
        raise ValueError("The imported board needs finite board bounds.")
    xmin, ymin, xmax, ymax = (_number(value, "board bound") for value in bounds)
    if xmax <= xmin or ymax <= ymin:
        raise ValueError("Imported board bounds must have positive width and height.")
    ambient = _number(request.get("ambient_temperature_c"), "ambient_temperature_c")
    if ambient < -273.15:
        raise ValueError("Ambient temperature is below absolute zero.")
    conductivity = _number(raw_board.get("conductivity_w_mk"), "board conductivity_w_mk", positive=True)
    thickness_m = _number(raw_board.get("thickness_mm"), "board thickness_mm", positive=True) * 1e-3
    spacing = _number(raw_board.get("grid_step_mm"), "board grid_step_mm", positive=True)
    h_top = _number(raw_board.get("convection_top_w_m2k"), "board convection_top_w_m2k")
    h_bottom = _number(raw_board.get("convection_bottom_w_m2k"), "board convection_bottom_w_m2k")
    if h_top < 0 or h_bottom < 0 or h_top + h_bottom <= 0:
        raise ValueError("At least one nonnegative board convection coefficient must be positive.")
    nx, ny = math.ceil((xmax - xmin) / spacing), math.ceil((ymax - ymin) / spacing)
    if nx < 1 or ny < 1 or nx * ny > MAX_CELLS:
        raise ValueError(f"Board grid exceeds the {MAX_CELLS}-cell limit; increase grid_step_mm.")
    dx_m, dy_m = (xmax - xmin) * 1e-3 / nx, (ymax - ymin) * 1e-3 / ny
    dx_mm, dy_mm = dx_m * 1e3, dy_m * 1e3
    cell_area = dx_m * dy_m
    sink_g = (h_top + h_bottom) * cell_area
    gx = conductivity * thickness_m * dy_m / dx_m
    gy = conductivity * thickness_m * dx_m / dy_m
    count = nx * ny
    pad_rows = [row for row in raw_parts if isinstance(row, Mapping) and row.get("contact_mode") == "pads"]
    matrix = lil_matrix((count + len(pad_rows), count + len(pad_rows)), dtype=float)
    rhs = np.zeros(count + len(pad_rows), dtype=float)
    rhs[:count] = sink_g * ambient
    for iy in range(ny):
        for ix in range(nx):
            index = iy * nx + ix
            diagonal = sink_g
            for neighbor, conductance in (
                (index - 1 if ix else None, gx),
                (index + 1 if ix + 1 < nx else None, gx),
                (index - nx if iy else None, gy),
                (index + nx if iy + 1 < ny else None, gy),
            ):
                if neighbor is not None:
                    diagonal += conductance
                    matrix[index, neighbor] = -conductance
            matrix[index, index] = diagonal
    # Desktop KiCad parsing uses ``ref`` while normalized DesignIR imports use
    # ``reference``. Both retain the same source coordinates in millimetres.
    available = {str(item.get("reference") or item.get("ref") or ""): item
                 for item in design.components if isinstance(item, Mapping)}
    admitted: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_power = 0.0
    next_case_node = count
    for raw in raw_parts:
        if not isinstance(raw, Mapping):
            raise ValueError("Each component assignment must be an object.")
        ref = str(raw.get("component_ref", "")).strip()
        if not ref or ref.casefold() in seen or ref not in available:
            raise ValueError(f"Thermal component {ref!r} is duplicated or absent from the imported board.")
        seen.add(ref.casefold())
        x, y = _point(available[ref], ref)
        if x < xmin or x > xmax or y < ymin or y > ymax:
            raise ValueError(f"{ref} lies outside the admitted board bounds.")
        power = _number(raw.get("power_w"), f"{ref} power_w")
        r_jc = _number(raw.get("r_junction_case_k_w"), f"{ref} r_junction_case_k_w", positive=True)
        r_cb = _number(raw.get("r_case_board_k_w"), f"{ref} r_case_board_k_w", positive=True)
        if power < 0:
            raise ValueError(f"{ref} power_w cannot be negative.")
        ix = min(nx - 1, int((x - xmin) / dx_mm))
        iy = min(ny - 1, int((y - ymin) / dy_mm))
        mode = raw.get("contact_mode", "square")
        if mode == "pads":
            contacts = _pad_contacts(design, ref, (xmin, ymin, xmax, ymax), (nx, ny), (dx_mm, dy_mm))
            if not contacts:
                raise ValueError(f"{ref} has no admitted copper pad land; choose an explicit square fallback or fix the import.")
            total_area = sum(contact["area_mm2"] for contact in contacts)
            case_node = next_case_node
            next_case_node += 1
            rhs[case_node] = power
            conductances = []
            for contact in contacts:
                conductance = contact["area_mm2"] / (total_area * r_cb)
                conductances.append(conductance)
                weights = contact["_weights"]
                matrix[case_node, case_node] += conductance
                for j, wj in weights:
                    matrix[j, case_node] -= conductance * wj
                    matrix[case_node, j] -= conductance * wj
                    for k, wk in weights:
                        matrix[j, k] += conductance * wj * wk
            admitted.append({"component_ref": ref, "position_mm": [x, y], "cell": [ix, iy],
                             "power_w": power, "contact_mode": "pads", "pad_count": len(contacts),
                             "r_junction_case_k_w": r_jc, "r_case_board_k_w": r_cb,
                             "_case_node": case_node, "_contacts": contacts,
                             "_conductances": conductances})
        elif mode == "square":
            contact_size = _number(raw.get("contact_size_mm"), f"{ref} contact_size_mm", positive=True)
            half = contact_size / 2
            if x - half < xmin or x + half > xmax or y - half < ymin or y + half > ymax:
                raise ValueError(f"{ref} board contact area extends outside board bounds.")
            weights: list[tuple[int, float]] = []
            for cy in range(ny):
                low_y, high_y = ymin + cy * dy_mm, ymin + (cy + 1) * dy_mm
                overlap_y = max(0.0, min(high_y, y + half) - max(low_y, y - half))
                if overlap_y <= 0:
                    continue
                for cx in range(nx):
                    low_x, high_x = xmin + cx * dx_mm, xmin + (cx + 1) * dx_mm
                    overlap_x = max(0.0, min(high_x, x + half) - max(low_x, x - half))
                    if overlap_x > 0:
                        weights.append((cy * nx + cx, overlap_x * overlap_y / (contact_size * contact_size)))
            if not weights or abs(sum(weight for _, weight in weights) - 1) > 1e-10:
                raise ValueError(f"{ref} contact area was not conserved on the board grid.")
            for index, weight in weights:
                rhs[index] += power * weight
            admitted.append({"component_ref": ref, "position_mm": [x, y], "cell": [ix, iy],
                             "power_w": power, "contact_mode": "square", "contact_size_mm": contact_size,
                             "r_junction_case_k_w": r_jc, "r_case_board_k_w": r_cb,
                             "_weights": weights})
        else:
            raise ValueError(f"{ref} contact_mode must be pads or square.")
        total_power += power
    if not math.isfinite(total_power):
        raise ValueError("Total power exceeds the finite numerical range.")
    coefficients = matrix.tocsc()
    values = np.asarray(spsolve(coefficients, rhs), dtype=float)
    if values.shape != (count + len(pad_rows),) or not np.all(np.isfinite(values)) or np.min(values) < -273.15:
        raise ValueError("Board thermal system returned invalid temperatures.")
    residual = np.asarray(coefficients @ values - rhs, dtype=float)
    relative = float(np.linalg.norm(residual) / max(np.linalg.norm(rhs), 1e-30))
    rejected = float(np.sum(sink_g * (values[:count] - ambient)))
    energy_error = rejected - total_power
    if relative > 1e-9 or abs(energy_error) > 1e-8 * max(1.0, total_power):
        raise ValueError("Board thermal residual or energy balance did not pass.")
    for item in admitted:
        if item["contact_mode"] == "pads":
            contacts = item.pop("_contacts")
            conductances = item.pop("_conductances")
            case_temp = float(values[item.pop("_case_node")])
            for contact, conductance in zip(contacts, conductances):
                pad_temp = float(sum(values[index] * weight for index, weight in contact.pop("_weights")))
                contact["board_temperature_c"] = pad_temp
                contact["heat_w"] = conductance * (case_temp - pad_temp)
            if abs(sum(contact["heat_w"] for contact in contacts) - item["power_w"]) > 1e-8 * max(1, item["power_w"]):
                raise ValueError("Pad heat flow did not conserve component power.")
            item["pad_contacts"] = contacts
            board_temp = float(sum(contact["board_temperature_c"] * contact["area_mm2"] for contact in contacts)
                               / sum(contact["area_mm2"] for contact in contacts))
        else:
            board_temp = float(sum(values[index] * weight for index, weight in item.pop("_weights")))
            case_temp = board_temp + item["power_w"] * item["r_case_board_k_w"]
        junction_temp = case_temp + item["power_w"] * item["r_junction_case_k_w"]
        if not all(math.isfinite(value) for value in (case_temp, junction_temp)):
            raise ValueError("A component temperature exceeds the finite numerical range.")
        item.update(board_temperature_c=board_temp, case_temperature_c=case_temp,
                    junction_temperature_c=junction_temp)
    return {
        "contract": CONTRACT, "status": "completed", "model_status": "approximate",
        "grid": {"origin_mm": [xmin, ymin], "spacing_mm": [dx_mm, dy_mm],
                 "shape": [nx, ny], "temperatures_c": values[:count].tolist(), "order": "x-fast"},
        "components": admitted,
        "summary": {"minimum_board_temperature_c": float(np.min(values[:count])),
                    "maximum_board_temperature_c": float(np.max(values[:count])),
                    "maximum_junction_temperature_c": max(item["junction_temperature_c"] for item in admitted),
                    "total_power_w": total_power, "outward_heat_w": rejected,
                    "energy_balance_error_w": energy_error, "linear_relative_residual": relative},
        "provenance": {"solver_id": "spike.board_plate_thermal", "design_id": design.design_id,
                       "board_model": "uniform_axis_aligned_bounding_rectangle",
                       "boundary_model": "adiabatic_edges_and_uniform_top_bottom_convection",
                       "component_model": "square_contact_or_imported_copper_pad_case_coupling",
                       "production_qualified": False, "request": dict(request)},
        "issues": [{"code": "BOARD_THERMAL_APPROXIMATE_GEOMETRY", "severity": "warning",
                    "message": "Board bounds are a uniform plate; cutouts, copper patterns, package/case gradients, airflow, radiation, and measured heat paths are not modeled."}],
    }


def run_board_thermal(design: DesignIR, request: Mapping[str, Any]) -> dict[str, Any]:
    """Solve an explicit steady board-plate model or return a blocking diagnostic."""
    try:
        return _solve(design, request)
    except CopperGeometryError as exc:
        return {"contract": CONTRACT, "status": "blocked", "model_status": "failed",
                "grid": None, "components": [], "summary": {}, "issues": exc.diagnostics,
                "provenance": {"solver_id": "spike.layered_board_thermal", "production_qualified": False}}
    except (ValueError, TypeError, OverflowError, ArithmeticError) as exc:
        return {"contract": CONTRACT, "status": "blocked", "model_status": "failed",
                "grid": None, "components": [], "summary": {},
                "issues": [{"code": "BOARD_THERMAL_INPUT_INVALID", "severity": "error", "message": str(exc)}],
                "provenance": {"solver_id": "spike.board_plate_thermal", "production_qualified": False}}


__all__ = ["CONTRACT", "MAX_CELLS", "run_board_thermal"]
