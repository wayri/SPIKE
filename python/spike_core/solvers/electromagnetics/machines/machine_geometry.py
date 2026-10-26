# SPDX-License-Identifier: Apache-2.0
"""Deterministic planar triangle geometry for magnetic machines.

This module builds geometry and source attribution only.  It does not solve a
field, estimate force or torque, or imply eddy-current or thermal support.
The PM builder provides a conforming polar mesh and an explicitly approximate
fixed Cartesian compatibility mode.  Callers must refine ``target_edge_m`` and
check convergence for every quantity of interest.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Mapping, Sequence

import numpy as np


CONTRACT = "spike/magnetic-planar-triangle-mesh/v1"
MAX_AXIS_NODES = 501
MAX_TRIANGLES = 500_000


class MachineGeometryError(ValueError):
    """Raised before invalid geometry reaches a field solver."""


def _finite(name: str, value: float, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MachineGeometryError(f"{name} must be a real number.")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise MachineGeometryError(f"{name} must be {'positive and finite' if positive else 'finite'}.")
    return result


def _integer(name: str, value: int, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise MachineGeometryError(f"{name} must be an integer >= {minimum}.")
    return value


def _grid(half_width_m: float, half_height_m: float, target_edge_m: float,
          ) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    return _aligned_grid(half_width_m, half_height_m, target_edge_m, (), ())


def _aligned_grid(
    half_width_m: float,
    half_height_m: float,
    target_edge_m: float,
    mandatory_x_m: Sequence[float],
    mandatory_y_m: Sequence[float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    def axis(lower: float, upper: float, mandatory: Sequence[float]) -> np.ndarray:
        breaks = sorted({lower, upper, *(float(value) for value in mandatory
                                          if lower < float(value) < upper)})
        values = [lower]
        for left, right in zip(breaks, breaks[1:]):
            count = max(1, math.ceil((right - left) / target_edge_m))
            values.extend(float(value) for value in np.linspace(left, right, count + 1)[1:])
        return np.asarray(values, dtype=float)

    xs = axis(-half_width_m, half_width_m, mandatory_x_m)
    ys = axis(-half_height_m, half_height_m, mandatory_y_m)
    nx, ny = len(xs) - 1, len(ys) - 1
    if len(xs) > MAX_AXIS_NODES or len(ys) > MAX_AXIS_NODES:
        raise MachineGeometryError(
            f"Requested refinement exceeds {MAX_AXIS_NODES} nodes on one axis."
        )
    triangle_count = 2 * nx * ny
    if triangle_count > MAX_TRIANGLES:
        raise MachineGeometryError(
            f"Requested refinement exceeds {MAX_TRIANGLES} triangles."
        )
    xx, yy = np.meshgrid(xs, ys)
    nodes = np.column_stack((xx.ravel(), yy.ravel()))
    triangles = np.empty((triangle_count, 3), dtype=np.int64)
    cursor = 0
    for j in range(ny):
        row = j * (nx + 1)
        for i in range(nx):
            lower_left = row + i
            lower_right = lower_left + 1
            upper_left = lower_left + nx + 1
            upper_right = upper_left + 1
            triangles[cursor] = (lower_left, lower_right, upper_right)
            triangles[cursor + 1] = (lower_left, upper_right, upper_left)
            cursor += 2
    boundary = np.unique(np.concatenate((
        np.arange(nx + 1, dtype=np.int64),
        np.arange(ny * (nx + 1), (ny + 1) * (nx + 1), dtype=np.int64),
        np.arange(0, (ny + 1) * (nx + 1), nx + 1, dtype=np.int64),
        np.arange(nx, (ny + 1) * (nx + 1), nx + 1, dtype=np.int64),
    )))
    return (nodes, triangles, boundary, float(np.max(np.diff(xs))),
            float(np.max(np.diff(ys))))


def _polar_grid(
    outer_radius_m: float,
    target_edge_m: float,
    interface_radii_m: Sequence[float],
    mandatory_angles_rad: Sequence[float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float, list[float], list[float]]:
    """Create common-angle concentric rings with exact requested ring vertices."""
    radial_breaks = [0.0, *sorted({float(value) for value in interface_radii_m})]
    if radial_breaks[-1] != outer_radius_m:
        radial_breaks.append(outer_radius_m)
    if (radial_breaks[0] != 0.0 or radial_breaks[-1] != outer_radius_m
            or any(right <= left for left, right in zip(radial_breaks, radial_breaks[1:]))):
        raise MachineGeometryError("Polar interface radii must increase inside the outer boundary.")
    radii: list[float] = []
    for left, right in zip(radial_breaks, radial_breaks[1:]):
        count = max(1, math.ceil((right - left) / target_edge_m))
        radii.extend(float(value) for value in np.linspace(left, right, count + 1)[1:])

    two_pi = 2.0 * math.pi
    mandatory: list[float] = []
    for raw in sorted(float(value) % two_pi for value in mandatory_angles_rad):
        if not mandatory or abs(raw - mandatory[-1]) > 64.0 * np.finfo(float).eps:
            mandatory.append(raw)
    regular_count = max(16, math.ceil(two_pi * outer_radius_m / (0.7 * target_edge_m)))
    regular_step = two_pi / regular_count

    def circular_distance(left: float, right: float) -> float:
        delta = abs(left - right)
        return min(delta, two_pi - delta)

    regular = [index * regular_step for index in range(regular_count)]
    proximity = 0.18 * regular_step
    angles = sorted(mandatory + [
        angle for angle in regular
        if all(circular_distance(angle, edge) >= proximity for edge in mandatory)
    ])
    deduplicated: list[float] = []
    for angle in angles:
        if not deduplicated or angle - deduplicated[-1] > 64.0 * np.finfo(float).eps:
            deduplicated.append(angle)
    angles = deduplicated
    if len(angles) < 8:
        raise MachineGeometryError("Polar mesh requires at least eight angular sectors.")
    circular_steps = np.diff(np.asarray([*angles, angles[0] + two_pi]))
    if float(np.min(circular_steps)) <= 1e-12:
        raise MachineGeometryError(
            "Rotor and stator angular interfaces nearly coincide; adjust angle or refinement."
        )

    sectors, rings = len(angles), len(radii)
    triangle_count = sectors * (1 + 2 * (rings - 1))
    node_count = 1 + sectors * rings
    if triangle_count > MAX_TRIANGLES or node_count > 100_000:
        raise MachineGeometryError("Requested polar refinement exceeds the mesh resource budget.")
    nodes = np.empty((node_count, 2), dtype=float)
    nodes[0] = (0.0, 0.0)
    angle_array = np.asarray(angles)
    directions = np.column_stack((np.cos(angle_array), np.sin(angle_array)))
    for ring_index, radius in enumerate(radii):
        start = 1 + ring_index * sectors
        nodes[start:start + sectors] = radius * directions
    triangles = np.empty((triangle_count, 3), dtype=np.int64)
    cursor = 0
    first = 1
    for angle_index in range(sectors):
        triangles[cursor] = (0, first + angle_index, first + (angle_index + 1) % sectors)
        cursor += 1
    for ring_index in range(rings - 1):
        inner = 1 + ring_index * sectors
        outer = inner + sectors
        for angle_index in range(sectors):
            following = (angle_index + 1) % sectors
            triangles[cursor] = (inner + angle_index, outer + angle_index, outer + following)
            triangles[cursor + 1] = (inner + angle_index, outer + following, inner + following)
            cursor += 2
    boundary = np.arange(1 + (rings - 1) * sectors, 1 + rings * sectors, dtype=np.int64)
    maximum_radial_step = max(
        radii[0], *(right - left for left, right in zip(radii, radii[1:]))
    )
    maximum_outer_chord = float(2.0 * outer_radius_m * np.sin(0.5 * np.max(circular_steps)))
    return (
        nodes, triangles, boundary, float(maximum_radial_step), maximum_outer_chord,
        radii, angles,
    )


def _material(
    mu_r: float,
    *,
    remanence_t: Sequence[float] = (0.0, 0.0),
    conductivity_s_m: float = 0.0,
) -> dict[str, Any]:
    return {"mu_r": float(mu_r),
            "remanence_t": [float(remanence_t[0]), float(remanence_t[1])],
            "conductivity_s_m": float(conductivity_s_m)}


def _steel_material(
    relative_permeability: float,
    bh_curve: Sequence[Sequence[float]] | None,
    conductivity_s_m: float,
) -> dict[str, Any]:
    if bh_curve is None:
        return _material(relative_permeability, conductivity_s_m=conductivity_s_m)
    if (not isinstance(bh_curve, Sequence) or isinstance(bh_curve, (str, bytes))
            or len(bh_curve) < 2
            or any(not isinstance(pair, Sequence) or isinstance(pair, (str, bytes))
                   or len(pair) != 2 for pair in bh_curve)):
        raise MachineGeometryError(
            "steel_bh_curve must contain at least two [B_t, H_a_per_m] pairs."
        )
    try:
        curve = [[float(pair[0]), float(pair[1])] for pair in bh_curve]
    except (TypeError, ValueError, OverflowError) as exc:
        raise MachineGeometryError("steel_bh_curve values must be real numbers.") from exc
    if (curve[0] != [0.0, 0.0]
            or any(not all(math.isfinite(value) for value in pair) for pair in curve)
            or any(curve[index][0] <= curve[index - 1][0]
                   or curve[index][1] <= curve[index - 1][1]
                   for index in range(1, len(curve)))):
        raise MachineGeometryError(
            "steel_bh_curve must start at [0, 0] and have strictly increasing finite B and H."
        )
    return {
        "bh_curve": curve,
        "remanence_t": [0.0, 0.0],
        "conductivity_s_m": float(conductivity_s_m),
    }


def _finish_mesh(
    *,
    model: str,
    nodes: np.ndarray,
    triangles: np.ndarray,
    boundary_nodes: np.ndarray,
    classify: Callable[[float, float], tuple[str, float]],
    materials: Mapping[str, Mapping[str, Any]],
    material_roles: Mapping[str, str],
    stack_depth_m: float,
    target_edge_m: float,
    actual_dx_m: float,
    actual_dy_m: float,
    motion: Mapping[str, Any],
    geometry: Mapping[str, Any],
    meshing: Mapping[str, Any] | None = None,
    limitations: Sequence[str] | None = None,
) -> dict[str, Any]:
    centroids = nodes[triangles].mean(axis=1)
    region_ids = np.empty(len(triangles), dtype=object)
    current_density = np.empty(len(triangles), dtype=float)
    for index, (x_coordinate, y_coordinate) in enumerate(centroids):
        region, current = classify(float(x_coordinate), float(y_coordinate))
        region_ids[index] = region
        current_density[index] = current
    missing_regions = set(materials) - {str(value) for value in region_ids}
    if missing_regions:
        raise MachineGeometryError(
            "target_edge_m is too coarse to represent regions: "
            + ", ".join(sorted(missing_regions))
        )
    mesh: dict[str, Any] = {
        "contract": CONTRACT,
        "model": model,
        "units": {
            "coordinates": "m",
            "stack_depth": "m",
            "current_density": "A/m^2",
            "remanence": "T",
            "conductivity": "S/m",
        },
        "nodes_m": nodes,
        "triangles": triangles,
        "region_ids": region_ids.tolist(),
        "materials": {key: dict(value) for key, value in materials.items()},
        "material_roles": dict(material_roles),
        "current_density_a_m2": current_density.tolist(),
        "boundary_nodes": [int(value) for value in boundary_nodes],
        "stack_depth_m": float(stack_depth_m),
        "motion": dict(motion),
        "geometry": dict(geometry),
        "meshing": dict(meshing or {
            "method": "fixed_cartesian_background_centroid_attribution",
            "model_status": "approximate",
            "target_edge_m": float(target_edge_m),
            "actual_edge_x_m": actual_dx_m,
            "actual_edge_y_m": actual_dy_m,
            "sliding_interface": False,
            "conforming_material_interfaces": False,
            "refinement_parameter": "target_edge_m",
        }),
        "limitations": list(limitations or [
            "Material interfaces are stair-step approximations from triangle-centroid attribution.",
            "Moving parts are re-attributed on one fixed background mesh; there is no sliding interface.",
            "Geometry generation does not establish mesh convergence, field accuracy, force, torque, loss, or thermal validity.",
            "Conductivity is material metadata only; this geometry module does not solve eddy currents.",
            "Numerical code requires knowledgeable human review before release.",
        ]),
    }
    return validate_machine_mesh(mesh)


def build_pm_machine_mesh(
    *,
    rotor_angle_rad: float = 0.0,
    target_edge_m: float = 0.002,
    mesh_method: str = "polar_conforming",
    air_box_half_extent_m: float = 0.05,
    rotor_core_radius_m: float = 0.010,
    magnet_outer_radius_m: float = 0.014,
    stator_inner_radius_m: float = 0.020,
    stator_outer_radius_m: float = 0.035,
    slot_outer_radius_m: float = 0.029,
    slot_angular_fraction: float = 0.44,
    pole_pairs: int = 2,
    slots: int = 6,
    winding_current_density_a_m2: float = 0.0,
    magnet_remanence_t: float = 1.2,
    steel_relative_permeability: float = 1000.0,
    steel_bh_curve: Sequence[Sequence[float]] | None = None,
    steel_conductivity_s_m: float = 2.0e6,
    magnet_conductivity_s_m: float = 6.25e5,
    winding_conductivity_s_m: float = 5.8e7,
    stack_depth_m: float = 0.04,
) -> dict[str, Any]:
    """Build a radial-flux PM rotor and slotted stator cross-section in SI units."""
    rotor_angle = _finite("rotor_angle_rad", rotor_angle_rad)
    target_edge = _finite("target_edge_m", target_edge_m, positive=True)
    box = _finite("air_box_half_extent_m", air_box_half_extent_m, positive=True)
    rotor_core = _finite("rotor_core_radius_m", rotor_core_radius_m, positive=True)
    magnet_outer = _finite("magnet_outer_radius_m", magnet_outer_radius_m, positive=True)
    stator_inner = _finite("stator_inner_radius_m", stator_inner_radius_m, positive=True)
    stator_outer = _finite("stator_outer_radius_m", stator_outer_radius_m, positive=True)
    slot_outer = _finite("slot_outer_radius_m", slot_outer_radius_m, positive=True)
    slot_fraction = _finite("slot_angular_fraction", slot_angular_fraction, positive=True)
    pairs = _integer("pole_pairs", pole_pairs, minimum=1)
    slot_count = _integer("slots", slots, minimum=2)
    if slot_count % 2:
        raise MachineGeometryError("slots must be even so the planar winding source has zero net Jz.")
    if not (rotor_core < magnet_outer < stator_inner < slot_outer < stator_outer < box):
        raise MachineGeometryError(
            "Radii must satisfy rotor_core < magnet_outer < stator_inner < slot_outer < stator_outer < air box."
        )
    if not 0.0 < slot_fraction < 0.9:
        raise MachineGeometryError("slot_angular_fraction must be between 0 and 0.9.")
    current_density = _finite(
        "winding_current_density_a_m2", winding_current_density_a_m2
    )
    remanence = _finite("magnet_remanence_t", magnet_remanence_t, positive=True)
    steel_mu = _finite("steel_relative_permeability", steel_relative_permeability, positive=True)
    steel_sigma = _finite("steel_conductivity_s_m", steel_conductivity_s_m)
    magnet_sigma = _finite("magnet_conductivity_s_m", magnet_conductivity_s_m)
    winding_sigma = _finite("winding_conductivity_s_m", winding_conductivity_s_m)
    depth = _finite("stack_depth_m", stack_depth_m, positive=True)
    if min(steel_sigma, magnet_sigma, winding_sigma) < 0.0:
        raise MachineGeometryError("Material conductivities must be nonnegative.")
    if mesh_method not in {"polar_conforming", "fixed_cartesian"}:
        raise MachineGeometryError("mesh_method must be polar_conforming or fixed_cartesian.")

    pole_count = 2 * pairs
    pole_pitch = 2.0 * math.pi / pole_count
    slot_pitch = 2.0 * math.pi / slot_count
    stress_radius = 0.5 * (magnet_outer + stator_inner)
    if mesh_method == "polar_conforming":
        magnet_edges = [rotor_angle + pole * pole_pitch for pole in range(pole_count)]
        slot_centers = [slot * slot_pitch for slot in range(slot_count)]
        half_slot = 0.5 * slot_fraction * slot_pitch
        slot_edges = [
            angle
            for center in slot_centers
            for angle in (center - half_slot, center + half_slot)
        ]
        nodes, triangles, boundary, dx, dy, polar_radii, polar_angles = _polar_grid(
            box,
            target_edge,
            [
                rotor_core, magnet_outer, stress_radius, stator_inner,
                slot_outer, stator_outer, box,
            ],
            [*magnet_edges, *slot_centers, *slot_edges],
        )
        meshing = {
            "method": "polar_conforming",
            "model_status": "approximate",
            "target_edge_m": target_edge,
            "maximum_radial_step_m": dx,
            "maximum_outer_chord_m": dy,
            "outer_boundary_shape": "circle",
            "outer_boundary_radius_m": box,
            "sliding_interface": False,
            "moving_remesh": True,
            "conforming_material_interfaces": True,
            "curved_interfaces": "inscribed_polygon_facets",
            "interface_radii_m": [
                rotor_core, magnet_outer, stator_inner, slot_outer, stator_outer,
            ],
            "stress_sampling_radius_m": stress_radius,
            "radial_ring_count": len(polar_radii),
            "angular_sector_count": len(polar_angles),
            "mandatory_interface_angles_rad": sorted(
                {float(angle % (2.0 * math.pi)) for angle in [*magnet_edges, *slot_centers, *slot_edges]}
            ),
            "refinement_parameter": "target_edge_m",
        }
        mesh_limits = ["Circular material interfaces are conforming inscribed polygons; curved-geometry error requires mesh refinement.",
                       "Every rotor position is remeshed; there is no sliding interface or moving-conductor field transport.",
                       "Geometry generation does not establish mesh, outer-boundary, force, torque, loss, or thermal convergence.",
                       "Conductivity is material metadata only; this geometry module does not solve eddy currents.",
                       "Numerical code requires knowledgeable human review before release."]
    else:
        nodes, triangles, boundary, dx, dy = _grid(box, box, target_edge)
        meshing = {
            "method": "fixed_cartesian_background_centroid_attribution",
            "model_status": "approximate",
            "target_edge_m": target_edge,
            "actual_edge_x_m": dx,
            "actual_edge_y_m": dy,
            "outer_boundary_shape": "square",
            "outer_boundary_half_extent_m": box,
            "sliding_interface": False,
            "moving_remesh": False,
            "conforming_material_interfaces": False,
            "refinement_parameter": "target_edge_m",
        }
        mesh_limits = ["Material interfaces are stair-step approximations from triangle-centroid attribution.",
                       "Moving parts are re-attributed on one fixed background mesh; there is no sliding interface.",
                       "Geometry generation does not establish mesh, air-boundary, force, torque, loss, or thermal convergence.",
                       "Conductivity is material metadata only; this geometry module does not solve eddy currents.",
                       "Numerical code requires knowledgeable human review before release."]
    materials: dict[str, dict[str, Any]] = {
        "air": _material(1.0),
        "rotor_steel": _steel_material(steel_mu, steel_bh_curve, steel_sigma),
        "stator_steel": _steel_material(steel_mu, steel_bh_curve, steel_sigma),
        "winding_pos": _material(1.0, conductivity_s_m=winding_sigma),
        "winding_neg": _material(1.0, conductivity_s_m=winding_sigma),
    }
    roles = {
        "air": "air",
        "rotor_steel": "moving_ferromagnetic_core",
        "stator_steel": "stationary_ferromagnetic_core",
        "winding_pos": "winding_positive_z",
        "winding_neg": "winding_negative_z",
    }
    for pole in range(pole_count):
        center_angle = rotor_angle + (pole + 0.5) * pole_pitch
        polarity = 1.0 if pole % 2 == 0 else -1.0
        region = f"magnet_{pole}"
        materials[region] = _material(
            1.05,
            remanence_t=(
                polarity * remanence * math.cos(center_angle),
                polarity * remanence * math.sin(center_angle),
            ),
            conductivity_s_m=magnet_sigma,
        )
        roles[region] = "moving_permanent_magnet"

    stress_angles = np.linspace(0.0, 2.0 * math.pi, 128, endpoint=False, dtype=float)
    stress_contour_open = np.column_stack((stress_radius * np.cos(stress_angles),
                                           stress_radius * np.sin(stress_angles)))
    stress_contour = np.vstack((stress_contour_open, stress_contour_open[0]))

    def classify(x_coordinate: float, y_coordinate: float) -> tuple[str, float]:
        radius = math.hypot(x_coordinate, y_coordinate)
        angle = math.atan2(y_coordinate, x_coordinate)
        if radius <= rotor_core:
            return "rotor_steel", 0.0
        if radius <= magnet_outer:
            local = (angle - rotor_angle) % (2.0 * math.pi)
            return f"magnet_{min(pole_count - 1, int(local / pole_pitch))}", 0.0
        if stator_inner <= radius <= stator_outer:
            slot_phase = ((angle + 0.5 * slot_pitch) % slot_pitch) - 0.5 * slot_pitch
            if radius <= slot_outer and abs(slot_phase) <= 0.5 * slot_fraction * slot_pitch:
                slot_index = int(((angle + 0.5 * slot_pitch) % (2.0 * math.pi)) / slot_pitch)
                if slot_index % 2 == 0:
                    return "winding_pos", current_density
                return "winding_neg", -current_density
            return "stator_steel", 0.0
        return "air", 0.0

    return _finish_mesh(
        model="pm_radial_flux_machine_2d",
        nodes=nodes,
        triangles=triangles,
        boundary_nodes=boundary,
        classify=classify,
        materials=materials,
        material_roles=roles,
        stack_depth_m=depth,
        target_edge_m=target_edge,
        actual_dx_m=dx,
        actual_dy_m=dy,
        motion={
            "kind": "rotation",
            "angle_rad": rotor_angle,
            "origin_m": [0.0, 0.0],
            "moving_regions": ["rotor_steel"] + [f"magnet_{pole}" for pole in range(pole_count)],
            "mover_region_ids": ["rotor_steel"] + [f"magnet_{pole}" for pole in range(pole_count)],
            "thermal_region_ids": ["rotor_steel", "stator_steel", "winding_pos", "winding_neg"]
            + [f"magnet_{pole}" for pole in range(pole_count)],
            "stress_contour_m": stress_contour,
            "stress_contour_orientation": "counterclockwise",
            "stress_contour_role": "air_gap_maxwell_stress_integration",
            "periodic_angle_rad": 2.0 * math.pi,
        },
        geometry={
            "air_box_half_extent_m": box,
            "outer_boundary_shape": "circle" if mesh_method == "polar_conforming" else "square",
            "rotor_core_radius_m": rotor_core,
            "magnet_outer_radius_m": magnet_outer,
            "stator_inner_radius_m": stator_inner,
            "slot_outer_radius_m": slot_outer,
            "stator_outer_radius_m": stator_outer,
            "pole_pairs": pairs,
            "slots": slot_count,
            "slot_angular_fraction": slot_fraction,
        },
        meshing=meshing,
        limitations=mesh_limits,
    )


def build_solenoid_mesh(
    *,
    plunger_position_m: float = 0.0,
    target_edge_m: float = 0.002,
    mesh_method: str = "aligned_cartesian",
    air_box_half_width_m: float = 0.05,
    air_box_half_height_m: float = 0.05,
    core_outer_width_m: float = 0.050,
    stationary_core_height_m: float = 0.025,
    core_leg_width_m: float = 0.008,
    yoke_thickness_m: float = 0.008,
    nominal_gap_m: float = 0.003,
    armature_width_m: float = 0.050,
    armature_thickness_m: float = 0.008,
    coil_clearance_m: float = 0.001,
    winding_current_density_a_m2: float = 0.0,
    steel_relative_permeability: float = 1000.0,
    steel_bh_curve: Sequence[Sequence[float]] | None = None,
    steel_conductivity_s_m: float = 2.0e6,
    winding_conductivity_s_m: float = 5.8e7,
    stack_depth_m: float = 0.04,
) -> dict[str, Any]:
    """Build a translating U-core actuator with two winding cross-sections."""
    displacement = _finite("plunger_position_m", plunger_position_m)
    target_edge = _finite("target_edge_m", target_edge_m, positive=True)
    half_width = _finite("air_box_half_width_m", air_box_half_width_m, positive=True)
    half_height = _finite("air_box_half_height_m", air_box_half_height_m, positive=True)
    outer_width = _finite("core_outer_width_m", core_outer_width_m, positive=True)
    core_height = _finite("stationary_core_height_m", stationary_core_height_m, positive=True)
    leg_width = _finite("core_leg_width_m", core_leg_width_m, positive=True)
    yoke = _finite("yoke_thickness_m", yoke_thickness_m, positive=True)
    nominal_gap = _finite("nominal_gap_m", nominal_gap_m, positive=True)
    armature_width = _finite("armature_width_m", armature_width_m, positive=True)
    armature_thickness = _finite("armature_thickness_m", armature_thickness_m, positive=True)
    clearance = _finite("coil_clearance_m", coil_clearance_m, positive=True)
    current_density = _finite("winding_current_density_a_m2", winding_current_density_a_m2)
    steel_mu = _finite("steel_relative_permeability", steel_relative_permeability, positive=True)
    steel_sigma = _finite("steel_conductivity_s_m", steel_conductivity_s_m)
    winding_sigma = _finite("winding_conductivity_s_m", winding_conductivity_s_m)
    depth = _finite("stack_depth_m", stack_depth_m, positive=True)
    if min(steel_sigma, winding_sigma) < 0.0:
        raise MachineGeometryError("Material conductivities must be nonnegative.")
    if not (2.0 * leg_width < outer_width <= 2.0 * half_width):
        raise MachineGeometryError("core_outer_width_m must fit the air box and exceed two leg widths.")
    if not (yoke < core_height < half_height):
        raise MachineGeometryError("stationary core height must exceed its yoke and fit the air box.")
    if armature_width > 2.0 * half_width:
        raise MachineGeometryError("armature_width_m must fit the air box.")
    actual_gap = nominal_gap + displacement
    armature_bottom = actual_gap
    armature_top = armature_bottom + armature_thickness
    if actual_gap <= 0.0 or armature_top >= half_height:
        raise MachineGeometryError("Plunger position must leave a positive gap and keep the armature in the air box.")
    coil_x_inner = 0.5 * outer_width - leg_width - clearance
    coil_x_outer = clearance
    coil_y_bottom = -core_height + yoke + clearance
    coil_y_top = -clearance
    if coil_x_inner <= coil_x_outer or coil_y_top <= coil_y_bottom:
        raise MachineGeometryError("Core windows are too small for the requested winding clearance.")
    if mesh_method not in {"aligned_cartesian", "fixed_cartesian"}:
        raise MachineGeometryError("mesh_method must be aligned_cartesian or fixed_cartesian.")
    half_core = 0.5 * outer_width
    half_armature = 0.5 * armature_width
    if mesh_method == "aligned_cartesian":
        nodes, triangles, boundary, dx, dy = _aligned_grid(
            half_width,
            half_height,
            target_edge,
            [
                -half_core, -half_core + leg_width,
                -coil_x_inner, -coil_x_outer, coil_x_outer, coil_x_inner,
                half_core - leg_width, half_core,
                -half_armature, half_armature,
            ],
            [
                -core_height, -core_height + yoke,
                coil_y_bottom, coil_y_top, 0.0,
                armature_bottom, armature_top,
            ],
        )
        meshing = {
            "method": "aligned_cartesian",
            "model_status": "approximate",
            "target_edge_m": target_edge,
            "maximum_edge_x_m": dx,
            "maximum_edge_y_m": dy,
            "outer_boundary_shape": "rectangle",
            "outer_boundary_half_width_m": half_width,
            "outer_boundary_half_height_m": half_height,
            "sliding_interface": False,
            "moving_remesh": True,
            "conforming_material_interfaces": True,
            "refinement_parameter": "target_edge_m",
        }
        mesh_limits = ["Axis-aligned material boundaries are conforming; every armature position is remeshed.",
                       "There is no sliding interface or moving-conductor field transport.",
                       "Geometry generation does not establish mesh, outer-boundary, force, loss, or thermal convergence.",
                       "Conductivity is material metadata only; this geometry module does not solve eddy currents.",
                       "Numerical code requires knowledgeable human review before release."]
    else:
        nodes, triangles, boundary, dx, dy = _grid(
            half_width, half_height, target_edge
        )
        meshing = {
            "method": "fixed_cartesian_background_centroid_attribution",
            "model_status": "approximate",
            "target_edge_m": target_edge,
            "actual_edge_x_m": dx,
            "actual_edge_y_m": dy,
            "outer_boundary_shape": "rectangle",
            "outer_boundary_half_width_m": half_width,
            "outer_boundary_half_height_m": half_height,
            "sliding_interface": False,
            "moving_remesh": False,
            "conforming_material_interfaces": False,
            "refinement_parameter": "target_edge_m",
        }
        mesh_limits = ["Material interfaces are stair-step approximations from triangle-centroid attribution.",
                       "Moving parts are re-attributed on one fixed background mesh; there is no sliding interface.",
                       "Geometry generation does not establish mesh, outer-boundary, force, loss, or thermal convergence.",
                       "Conductivity is material metadata only; this geometry module does not solve eddy currents.",
                       "Numerical code requires knowledgeable human review before release."]
    materials = {
        "air": _material(1.0),
        "stationary_steel": _steel_material(steel_mu, steel_bh_curve, steel_sigma),
        "armature_steel": _steel_material(steel_mu, steel_bh_curve, steel_sigma),
        "winding_pos": _material(1.0, conductivity_s_m=winding_sigma),
        "winding_neg": _material(1.0, conductivity_s_m=winding_sigma),
    }
    roles = {
        "air": "air",
        "stationary_steel": "stationary_ferromagnetic_core",
        "armature_steel": "moving_ferromagnetic_armature",
        "winding_pos": "winding_positive_z",
        "winding_neg": "winding_negative_z",
    }
    contour_margin = 0.25 * min(
        actual_gap,
        half_width - half_armature,
        half_height - armature_top,
    )
    if contour_margin <= 0.0:
        raise MachineGeometryError("Air box must leave clearance around the armature stress contour.")
    contour_left = -half_armature - contour_margin
    contour_right = half_armature + contour_margin
    contour_bottom = armature_bottom - contour_margin
    contour_top = armature_top + contour_margin
    stress_contour = np.asarray([[contour_left, contour_bottom],
                                 [contour_right, contour_bottom], [contour_right, contour_top],
                                 [contour_left, contour_top], [contour_left, contour_bottom]], dtype=float)

    def classify(x_coordinate: float, y_coordinate: float) -> tuple[str, float]:
        if (-half_armature <= x_coordinate <= half_armature
                and armature_bottom <= y_coordinate <= armature_top):
            return "armature_steel", 0.0
        in_yoke = (-half_core <= x_coordinate <= half_core
                   and -core_height <= y_coordinate <= -core_height + yoke)
        in_leg = (half_core - leg_width <= abs(x_coordinate) <= half_core
                  and -core_height <= y_coordinate <= 0.0)
        if in_yoke or in_leg:
            return "stationary_steel", 0.0
        in_coil_y = coil_y_bottom <= y_coordinate <= coil_y_top
        if in_coil_y and coil_x_outer <= x_coordinate <= coil_x_inner:
            return "winding_pos", current_density
        if in_coil_y and -coil_x_inner <= x_coordinate <= -coil_x_outer:
            return "winding_neg", -current_density
        return "air", 0.0

    return _finish_mesh(
        model="translating_u_core_solenoid_2d",
        nodes=nodes,
        triangles=triangles,
        boundary_nodes=boundary,
        classify=classify,
        materials=materials,
        material_roles=roles,
        stack_depth_m=depth,
        target_edge_m=target_edge,
        actual_dx_m=dx,
        actual_dy_m=dy,
        motion={
            "kind": "translation",
            "axis": [0.0, 1.0],
            "position_m": displacement,
            "nominal_gap_m": nominal_gap,
            "actual_gap_m": actual_gap,
            "moving_regions": ["armature_steel"],
            "mover_region_ids": ["armature_steel"],
            "thermal_region_ids": [
                "stationary_steel", "armature_steel", "winding_pos", "winding_neg"
            ],
            "stress_contour_m": stress_contour,
            "stress_contour_orientation": "counterclockwise",
            "stress_contour_role": "air_maxwell_stress_integration",
            "position_limits_m": {
                "lower_exclusive": -nominal_gap,
                "upper_exclusive": half_height - nominal_gap - armature_thickness,
            },
        },
        geometry={
            "air_box_half_width_m": half_width,
            "air_box_half_height_m": half_height,
            "core_outer_width_m": outer_width,
            "stationary_core_height_m": core_height,
            "core_leg_width_m": leg_width,
            "yoke_thickness_m": yoke,
            "armature_width_m": armature_width,
            "armature_thickness_m": armature_thickness,
            "coil_clearance_m": clearance,
        },
        meshing=meshing,
        limitations=mesh_limits,
    )


def validate_machine_mesh(mesh: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the solver-facing shape, finite values, and triangle orientation."""
    if not isinstance(mesh, Mapping) or mesh.get("contract") != CONTRACT:
        raise MachineGeometryError(f"Expected mesh contract {CONTRACT}.")
    try:
        nodes = np.asarray(mesh["nodes_m"], dtype=float)
        triangles = np.asarray(mesh["triangles"], dtype=np.int64)
        region_ids = np.asarray(mesh["region_ids"], dtype=object)
        current_density = np.asarray(mesh["current_density_a_m2"], dtype=float)
        boundary = np.asarray(mesh["boundary_nodes"], dtype=np.int64)
        materials = mesh["materials"]
        depth = float(mesh["stack_depth_m"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise MachineGeometryError("Mesh arrays or scalar fields are malformed.") from exc
    if nodes.ndim != 2 or nodes.shape[1] != 2 or len(nodes) < 3 or not np.isfinite(nodes).all():
        raise MachineGeometryError("nodes_m must be a finite N x 2 array.")
    if triangles.ndim != 2 or triangles.shape[1] != 3 or not 0 < len(triangles) <= MAX_TRIANGLES:
        raise MachineGeometryError("triangles must be a bounded M x 3 array.")
    if np.any(triangles < 0) or np.any(triangles >= len(nodes)):
        raise MachineGeometryError("Triangle node index is outside nodes_m.")
    points = nodes[triangles]
    twice_area = ((points[:, 1, 0] - points[:, 0, 0])
                  * (points[:, 2, 1] - points[:, 0, 1])
                  - (points[:, 1, 1] - points[:, 0, 1])
                  * (points[:, 2, 0] - points[:, 0, 0]))
    scale = max(float(np.ptp(nodes[:, 0])), float(np.ptp(nodes[:, 1])), 1.0)
    if np.any(twice_area <= 64.0 * np.finfo(float).eps * scale * scale):
        raise MachineGeometryError("Mesh contains a degenerate or clockwise triangle.")
    if region_ids.shape != (len(triangles),) or current_density.shape != (len(triangles),):
        raise MachineGeometryError("region_ids and current density must have one value per triangle.")
    if not np.isfinite(current_density).all():
        raise MachineGeometryError("Current density must be finite.")
    if not isinstance(materials, Mapping) or not materials:
        raise MachineGeometryError("materials must be a nonempty mapping.")
    used_regions = {str(value) for value in region_ids}
    if used_regions - set(materials):
        raise MachineGeometryError("Every used region must have a material record.")
    for region, material in materials.items():
        if not isinstance(region, str) or not region or not isinstance(material, Mapping):
            raise MachineGeometryError("Material region names and records are malformed.")
        remanence = np.asarray(material.get("remanence_t", (0.0, 0.0)), dtype=float)
        conductivity = float(material.get("conductivity_s_m", 0.0))
        if remanence.shape != (2,) or not np.isfinite(remanence).all():
            raise MachineGeometryError(f"Material {region} has invalid remanence_t.")
        if not math.isfinite(conductivity) or conductivity < 0.0:
            raise MachineGeometryError(f"Material {region} has invalid conductivity_s_m.")
        if "mu_r" in material:
            mu_r = float(material["mu_r"])
            if not math.isfinite(mu_r) or mu_r <= 0.0:
                raise MachineGeometryError(f"Material {region} has invalid mu_r.")
        elif "bh_curve" not in material:
            raise MachineGeometryError(f"Material {region} needs mu_r or bh_curve.")
    if boundary.ndim != 1 or len(boundary) < 4 or len(np.unique(boundary)) != len(boundary):
        raise MachineGeometryError("boundary_nodes must contain unique outer-boundary indexes.")
    if np.any(boundary < 0) or np.any(boundary >= len(nodes)):
        raise MachineGeometryError("Boundary node index is outside nodes_m.")
    if not math.isfinite(depth) or depth <= 0.0:
        raise MachineGeometryError("stack_depth_m must be positive and finite.")
    return dict(mesh)


__all__ = ["CONTRACT", "MachineGeometryError", "build_pm_machine_mesh", "build_solenoid_mesh", "validate_machine_mesh"]
