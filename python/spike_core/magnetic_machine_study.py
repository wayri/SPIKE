# SPDX-License-Identifier: Apache-2.0
"""Bounded planar geometry/field/mechanics study; not a 3D machine qualifier."""
from __future__ import annotations

import hashlib
import json
import math
import numpy as np


def _finite(value, name, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError(name + " must be finite" + (" and positive" if positive else ""))
    return float(value)


def maxwell_stress_integral(nodes, triangles, b_t, region_ids, contour_m, depth_m):
    """Integrate vacuum stress on a CCW air contour using exact triangle lookup.

    Exact integration of piecewise-constant element fields along straight edges.
    Shared-edge traces use the contour-interior side. Mesh refinement is required.
    Torque origin is (0,0). No field extrapolation outside the admitted mesh.
    """
    from scipy.spatial import cKDTree
    from .magnetic_fem import MU0
    nodes, raw_triangles = np.asarray(nodes, float), np.asarray(triangles)
    depth_m = _finite(depth_m, "stack_depth_m", True)
    if (nodes.ndim != 2 or nodes.shape[1] != 2 or not 3 <= len(nodes) <= 100_000
            or not np.all(np.isfinite(nodes)) or raw_triangles.ndim != 2 or raw_triangles.shape[1] != 3
            or not 1 <= len(raw_triangles) <= 200_000 or raw_triangles.dtype.kind not in "iu"
            or np.any(raw_triangles < 0) or np.any(raw_triangles >= len(nodes))
            or len(region_ids) != len(raw_triangles)):
        raise ValueError("Stress requires an admitted finite bounded triangle mesh and regions")
    triangles = raw_triangles.astype(int)
    b = np.asarray(b_t, float)
    contour = np.asarray(contour_m, float)
    if (contour.ndim != 2 or contour.shape[1] != 2 or not 4 <= len(contour) <= 8193
            or not np.all(np.isfinite(contour)) or not np.array_equal(contour[0], contour[-1])):
        raise ValueError("Stress contour must be a finite closed polygon")
    if b.shape != (len(triangles), 2) or not np.all(np.isfinite(b)):
        raise ValueError("Stress requires one finite B vector per triangle")
    segments = np.diff(contour, axis=0)
    mid = (contour[1:] + contour[:-1]) / 2
    area = np.sum(contour[:-1, 0]*contour[1:, 1]-contour[1:, 0]*contour[:-1, 1])/2
    if area <= 0 or np.any(np.linalg.norm(segments, axis=1) <= 0):
        raise ValueError("Stress contour must be counterclockwise without zero length segments")
    lower = np.minimum(contour[:-1], contour[1:])
    upper = np.maximum(contour[:-1], contour[1:])
    # Validate polygon simplicity before interpreting outward normals.
    def cross(a, c):
        return a[..., 0]*c[..., 1]-a[..., 1]*c[..., 0]
    for i, segment in enumerate(segments):
        candidates = np.flatnonzero(np.all(upper >= lower[i], axis=1)&np.all(lower <= upper[i], axis=1))
        candidates = candidates[candidates > i+1]
        if i == 0:
            candidates = candidates[candidates != len(segments)-1]
        if len(candidates):
            p, q = contour[candidates], contour[candidates+1]
            c1, c2 = cross(segment,p-contour[i]), cross(segment,q-contour[i])
            c3, c4 = cross(q-p,contour[i]-p), cross(q-p,contour[i+1]-p)
            if np.any((c1*c2 <= 0)&(c3*c4 <= 0)):
                raise ValueError("Stress contour must be simple (no intersecting segments)")
    vertices = nodes[triangles]
    centers = vertices.mean(axis=1)
    radius = float(np.max(np.linalg.norm(vertices-centers[:, None, :], axis=2)))
    tree = cKDTree(centers)
    force = np.zeros(2)
    torque = 0.
    pieces = 0
    unresolved_length = 0.
    # Clip every segment against triangle barycentric half-spaces. A union of
    # admitted air intervals must cover [0,1]; midpoint-only admission is unsafe.
    for start, end, midpoint in zip(contour[:-1], contour[1:], mid):
        candidates = np.asarray(tree.query_ball_point(midpoint, radius+np.linalg.norm(end-start)/2+1e-14), int)
        vv = vertices[candidates]
        e1, e2 = vv[:,1]-vv[:,0], vv[:,2]-vv[:,0]
        determinant = cross(e1,e2)
        scale = np.maximum(np.sum(e1*e1,axis=1),np.sum(e2*e2,axis=1))
        if np.any(np.abs(determinant) <= 1e-14*scale):
            raise ValueError("Stress mesh contains degenerate triangles")
        # Intersection parameters amplify coordinate roundoff by triangle
        # conditioning and the ratio of coordinate scale to segment length.
        length = np.linalg.norm(end-start)
        fraction_roundoff = (64*np.finfo(float).eps*max(length,float(np.max(np.abs(vv))))
                             *max(1.,float(np.max(scale/np.abs(determinant))))/length)
        if fraction_roundoff > 1e-7:
            raise ValueError("Stress contour intersection is ill-conditioned")
        first = np.column_stack((cross(start-vv[:,0],e2)/determinant,
                                 cross(e1,start-vv[:,0])/determinant))
        last = np.column_stack((cross(end-vv[:,0],e2)/determinant,
                                cross(e1,end-vv[:,0])/determinant))
        first = np.column_stack((1-first.sum(axis=1),first))
        last = np.column_stack((1-last.sum(axis=1),last))
        lo, hi = np.zeros(len(candidates)), np.ones(len(candidates))
        for coordinate in range(3):
            slope = last[:,coordinate]-first[:,coordinate]
            increasing, decreasing = slope > 0, slope < 0
            lo[increasing] = np.maximum(lo[increasing],-first[increasing,coordinate]/slope[increasing])
            hi[decreasing] = np.minimum(hi[decreasing],-first[decreasing,coordinate]/slope[decreasing])
            hi[(slope == 0)&(first[:,coordinate] < -1e-12)] = -1
        hit = hi > lo
        if any(str(region_ids[j]) != "air" for j in candidates[hit]):
            raise ValueError("Stress contour crosses non-air geometry; refine mesh or move contour")
        # Integrate each partition once. Exact clips avoid artificial expanded
        # overlaps. Roundoff-size endpoint gaps carry no assigned field.
        endpoints = np.unique(np.r_[0.,lo[hit],hi[hit],1.])
        direction = end-start
        for begin, finish in zip(endpoints[:-1],endpoints[1:]):
            fraction = .5*(begin+finish)
            covering = np.flatnonzero(hit&(lo <= fraction)&(hi >= fraction))
            if not len(covering):
                if finish-begin <= fraction_roundoff:
                    unresolved_length += length*(finish-begin)
                    continue
                raise ValueError(f"Stress contour leaves admitted air mesh (uncovered fraction {finish-begin:.3g})")
            if len(covering) > 1:
                # A contour on an air interface needs a defined one-sided
                # trace. CCW contour interior is left of its tangent.
                side = cross(direction,centers[candidates[covering]]-start)
                covering = covering[side > 0]
                if len(covering) != 1:
                    if finish-begin <= fraction_roundoff:
                        unresolved_length += length*(finish-begin)
                        continue
                    raise ValueError("Ambiguous overlapping stress mesh traces")
            field = b[candidates[covering[0]]]
            normal_ds = np.array([direction[1],-direction[0]])*(finish-begin)
            traction_ds = (field*np.dot(field,normal_ds)-.5*np.dot(field,field)*normal_ds)/MU0
            force += depth_m*traction_ds
            point = start+fraction*direction
            torque += depth_m*cross(point,traction_ds)
            pieces += 1
    if not np.all(np.isfinite(force)) or not math.isfinite(torque):
        raise ValueError("Stress integration exceeds numerical range")
    return {"force_x_n": float(force[0]), "force_y_n": float(force[1]), "torque_n_m": float(torque),
            "quadrature_segments": len(segments), "element_intervals": pieces,
            "roundoff_unresolved_contour_length_m": float(unresolved_length),
            "integration": "piecewise_constant_exact_contour_interior_trace", "torque_origin_m": [0., 0.]}


def run_magnetic_machine(request):
    from .machine_geometry import build_pm_machine_mesh, build_solenoid_mesh
    from .magnetic_fem import solve_magnetostatic
    if not isinstance(request, dict) or set(request)-{
        "contract", "model", "geometry", "mesh_edge_m", "stack_depth_m", "relative_permeability",
        "remanence_t", "current_density_a_m2", "position", "bh_curve", "motion", "transient"}:
        raise ValueError("Unknown magnetic machine study fields")
    if request.get("contract") != "spike/magnetic-machine-study/v1":
        raise ValueError("Unsupported magnetic machine study contract")
    model = request.get("model")
    if model not in {"pm_rotor", "solenoid"}:
        raise ValueError("Choose pm_rotor or solenoid")
    edge = _finite(request.get("mesh_edge_m", .002), "mesh_edge_m", True)
    depth = _finite(request.get("stack_depth_m", .02), "stack_depth_m", True)
    mu = _finite(request.get("relative_permeability", 1000), "relative_permeability", True)
    br = _finite(request.get("remanence_t", 1), "remanence_t")
    current = _finite(request.get("current_density_a_m2", 1e6), "current_density_a_m2")
    position = _finite(request.get("position", 0), "position")
    geometry = request.get("geometry", {})
    if not isinstance(geometry, dict):
        raise ValueError("geometry must be an object")
    if request.get("motion") is not None and request.get("transient") is not None:
        raise ValueError("Moving-conductor eddy/thermal coupling is unsupported; use stationary transient or quasi-static motion")
    if set(geometry) & {"rotor_angle_rad", "plunger_position_m", "target_edge_m", "stack_depth_m",
                        "winding_current_density_a_m2", "steel_relative_permeability",
                        "steel_bh_curve", "magnet_remanence_t"}:
        raise ValueError("Use top-level position, mesh, depth and current controls")
    factory = build_pm_machine_mesh if model == "pm_rotor" else build_solenoid_mesh

    def evaluate(q):
        kwargs = dict(geometry, target_edge_m=edge, winding_current_density_a_m2=current, stack_depth_m=depth)
        kwargs["rotor_angle_rad" if model == "pm_rotor" else "plunger_position_m"] = q
        mesh = factory(**kwargs)
        materials = {key: dict(value) for key, value in mesh["materials"].items()}
        for key, material in materials.items():
            if "ferromagnetic" in mesh["material_roles"][key]:
                if "bh_curve" in request:
                    material.pop("mu_r", None)
                    material.pop("relative_permeability", None)
                    material["bh_curve"] = request["bh_curve"]
                else:
                    material["mu_r"] = mu
            if np.any(material.get("remanence_t", [0, 0])):
                v = np.asarray(material["remanence_t"], float)
                material["remanence_t"] = (br*v/np.linalg.norm(v)).tolist()
        field = solve_magnetostatic(nodes_m=mesh["nodes_m"], triangles=mesh["triangles"],
            region_ids=mesh["region_ids"], materials=materials, stack_depth_m=depth,
            dirichlet_a_wb_per_m={int(i): 0. for i in mesh["boundary_nodes"]},
            current_density_a_per_m2=mesh["current_density_a_m2"], absolute_tolerance_a=1e-8)
        corners = np.asarray(mesh["motion"]["stress_contour_m"])
        pieces = []
        for start, end in zip(corners[:-1], corners[1:]):
            segments = max(1, math.ceil(np.linalg.norm(end-start)/(edge/4)))
            pieces.extend(start+(end-start)*fraction for fraction in np.arange(segments)/segments)
        contour = np.asarray([*pieces, pieces[0]])
        stress = maxwell_stress_integral(mesh["nodes_m"], mesh["triangles"], field["element_b_t"],
                                        mesh["region_ids"], contour, depth)
        return mesh, field, stress, materials, contour

    mesh, field, stress, materials, contour = evaluate(position)
    summary = {key: stress[key] for key in ("force_x_n", "force_y_n", "torque_n_m")}
    summary.update(max_b_t=float(np.max(np.linalg.norm(field["element_b_t"], axis=1))),
                   magnetic_energy_j=field["magnetic_energy_j"])
    histories = None
    if request.get("motion") is not None:
        spec = request["motion"]
        if not isinstance(spec, dict) or set(spec) != {
                "duration_s", "time_step_s", "mass_or_inertia", "damping", "external_load", "initial_velocity"}:
            raise ValueError("Motion requires duration, step, mass/inertia, damping, load and initial velocity")
        duration = _finite(spec["duration_s"], "duration_s", True)
        dt = _finite(spec["time_step_s"], "time_step_s", True)
        mass = _finite(spec["mass_or_inertia"], "mass_or_inertia", True)
        damping = _finite(spec["damping"], "damping")
        if damping < 0:
            raise ValueError("Damping must be nonnegative")
        load = _finite(spec["external_load"], "external_load")
        velocity = _finite(spec["initial_velocity"], "initial_velocity")
        count = math.ceil(duration/dt)
        if count > 100 or count*len(mesh["triangles"]) > 2_000_000:
            raise ValueError("Motion exceeds 100 steps or two million element steps")
        dt = duration/count
        histories = {"time_s": [0.], "position": [position], "velocity": [velocity],
                     "force_n_or_torque_nm": [stress["torque_n_m" if model == "pm_rotor" else "force_y_n"]]}
        for i in range(count):
            force = histories["force_n_or_torque_nm"][-1]
            # IMEX damped symplectic Euler; quasi-static field at every accepted position.
            velocity = (velocity+dt*(force+load)/mass)/(1+dt*damping/mass)
            position += dt*velocity
            mesh, field, stress, materials, contour = evaluate(position)
            histories["time_s"].append((i+1)*dt)
            histories["position"].append(position)
            histories["velocity"].append(velocity)
            histories["force_n_or_torque_nm"].append(stress["torque_n_m" if model == "pm_rotor" else "force_y_n"])
    result = {
        "contract": "spike/magnetic-machine-study-result/v1", "model": model,
        "model_status": "experimental", "production_qualified": False,
        "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        "summary": summary, "histories": histories,
        "field": {**field, "nodes_m": np.asarray(mesh["nodes_m"]).tolist(),
                  "triangles": np.asarray(mesh["triangles"]).tolist()},
        "force_method": "vacuum Maxwell stress; piecewise constant P1 B; midpoint contour quadrature",
        "stress_contour_m": contour.tolist(),
        "final_stress": stress,
        "geometry": {"dimensions": mesh["geometry"], "meshing": mesh["meshing"]},
        "limitations": [
            "Experimental planar extruded geometry; no sliding interface, transported moving-conductor state or 3D end fields.",
            "Mesh, air-box and stress-contour convergence are required before trusting force and torque.",
            "Motion is prescribed-current quasi-static mechanics, not voltage-driven field/circuit coupling; no moving-conductor eddy losses.",
            "No hysteresis, moving-body thermal coupling, demagnetization or manufacturing qualification.",
            "Knowledgeable numerical review is required before release.",
        ],
    }
    result["limitations"].extend(mesh["limitations"])
    result["validation"] = {"mesh_convergence": "not_established_for_this_request",
                            "force_torque_accuracy": "not_qualified",
                            "kernel_evidence": "independent_analytical_regressions"}
    # Final displayed field is tied to the final motion state; retain initial summary explicitly.
    if histories:
        result["summary_state"] = "initial_position"
        result["field_position"] = position
        result["final_stress"] = stress
    if request.get("transient") is not None:
        result["coupled"] = _run_stationary_transient(request["transient"], mesh, materials, depth, field)
        for frame in result["coupled"]["history"]:
            frame["max_temperature_k"] = max(frame["temperature_k"])
            if "element_joule_loss_w" in frame:
                frame["joule_loss_w"] = math.fsum(frame["element_joule_loss_w"])
        final = result["coupled"]["final_magnetic_result"]
        result["field"] = {**final, "nodes_m": np.asarray(mesh["nodes_m"]).tolist(),
                           "triangles": np.asarray(mesh["triangles"]).tolist()}
        result["final_stress"] = maxwell_stress_integral(mesh["nodes_m"], mesh["triangles"],
            final["element_b_t"], mesh["region_ids"], contour, depth)
        result["steady_reference_summary"] = result["summary"]
        result["summary"] = {key: result["final_stress"][key] for key in ("force_x_n", "force_y_n", "torque_n_m")}
        result["summary"].update(max_b_t=float(np.max(np.linalg.norm(final["element_b_t"], axis=1))),
                                magnetic_energy_j=final["magnetic_energy_j"])
        result["field_time_s"] = result["coupled"]["history"][-1]["time_s"]
        result["summary_state"] = "final_stationary_transient"
        result["limitations"].extend(result["coupled"]["limitations"])
    if len(json.dumps(result, allow_nan=False).encode()) > 24*1024*1024:
        raise ValueError("Machine result exceeds 24 MiB transport limit; coarsen mesh or increase snapshot stride")
    return result


def _run_stationary_transient(spec, mesh, materials, depth, static_field):
    from .magnetic_thermal import simulate_magnetic_thermal
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    import copy
    required = {"time_step_s", "steps", "thermal_materials", "initial_temperature_k",
                "ambient_temperature_k", "convection_h_w_m2_k", "initial_field"}
    optional = {"conductivity_temperature_coefficients", "snapshot_stride", "region_loss_density_w_m3"}
    if not isinstance(spec, dict) or not required <= set(spec) or set(spec)-required-optional:
        raise ValueError("Stationary transient requires explicit thermal materials, temperatures, convection, steps and initial field")
    if spec["initial_field"] not in {"zero", "steady"}:
        raise ValueError("initial_field must be zero or steady")
    initial = _finite(spec["initial_temperature_k"], "initial_temperature_k", True)
    ambient = _finite(spec["ambient_temperature_k"], "ambient_temperature_k", True)
    convection = _finite(spec["convection_h_w_m2_k"], "convection_h_w_m2_k")
    if convection < 0:
        raise ValueError("Convection coefficient must be nonnegative")
    triangles = np.asarray(mesh["triangles"], int)
    nodes = np.asarray(mesh["nodes_m"], float)
    # Separate disconnected electrical pieces; equal material names do not join
    # their induced-current constraints. Preserve explicit original-region lineage.
    region_ids = np.asarray(mesh["region_ids"], object).copy()
    original_regions = region_ids.copy()
    materials = copy.deepcopy(materials)
    thermal_materials = copy.deepcopy(spec["thermal_materials"])
    coefficients = copy.deepcopy(spec.get("conductivity_temperature_coefficients", {}))
    if not isinstance(thermal_materials, dict) or set(thermal_materials) != set(materials):
        raise ValueError("Thermal materials must exactly match original geometry regions")
    lineage = {}
    for key in list(materials):
        selected = np.flatnonzero(region_ids == key)
        if materials[key].get("conductivity_s_m", 0) <= 0 or not len(selected):
            lineage[key] = key
            continue
        tri = triangles[selected]
        vertices = np.unique(tri)
        rows = np.repeat(tri, 3, axis=1).ravel()
        cols = np.tile(tri, (1, 3)).ravel()
        graph = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(nodes), len(nodes))).tocsr()
        count, labels = connected_components(graph[vertices][:, vertices], directed=False)
        if count == 1:
            lineage[key] = key
            continue
        node_parts = np.full(len(nodes), -1, int)
        node_parts[vertices] = labels
        parts = node_parts[tri[:, 0]]
        old_material, old_thermal = materials.pop(key), thermal_materials.pop(key)
        old_coefficient = coefficients.pop(key, None)
        for part in range(count):
            new_key = key+"__conductor_"+str(part)
            region_ids[selected[parts == part]] = new_key
            materials[new_key] = dict(old_material)
            thermal_materials[new_key] = dict(old_thermal)
            lineage[new_key] = key
            if old_coefficient is not None:
                coefficients[new_key] = dict(old_coefficient)
    edges, counts = np.unique(np.sort(np.vstack((triangles[:, [0, 1]], triangles[:, [1, 2]],
                                                triangles[:, [2, 0]])), axis=1), axis=0, return_counts=True)
    exterior = edges[counts == 1]
    laws = spec.get("region_loss_density_w_m3", {})
    if not isinstance(laws, dict) or set(laws)-set(original_regions):
        raise ValueError("Loss densities must reference admitted material regions")
    for key, value in laws.items():
        if _finite(value, "region loss density") < 0:
            raise ValueError("Loss density must be nonnegative")
    area = np.asarray(static_field["element_area_m2"])
    if set(laws)-set(original_regions):
        raise ValueError("Loss densities must reference original geometry regions")
    loss = area*depth*np.asarray([laws.get(key, 0.) for key in original_regions])
    coupled = simulate_magnetic_thermal(nodes_m=nodes, triangles=triangles, region_ids=region_ids.tolist(),
        magnetic_materials=materials, thermal_materials=thermal_materials, stack_depth_m=depth,
        dirichlet_a_wb_per_m={int(i): 0. for i in mesh["boundary_nodes"]},
        initial_a_wb_per_m=static_field["potential_a_wb_per_m"] if spec["initial_field"] == "steady" else np.zeros(len(nodes)).tolist(),
        initial_temperature_k=np.full(len(nodes), initial).tolist(), time_step_s=spec["time_step_s"], steps=spec["steps"],
        conductivity_temperature_coefficients=coefficients,
        current_density_a_per_m2=mesh["current_density_a_m2"], winding_element_loss_w=loss.tolist(),
        convection_edges=[{"nodes": row.tolist(), "h_w_m2_k": convection, "ambient_temperature_k": ambient} for row in exterior] if convection else [],
        snapshot_stride=spec.get("snapshot_stride", 1), lumped_capacity=True)
    coupled["conductor_region_lineage"] = lineage
    return coupled
