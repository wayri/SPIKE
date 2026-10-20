# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Actual pinned STEP/OCC-to-creeping-flow benchmark; not turbulence qualification.

Boundary labels follow the known fixture equations, never inferred CAD intent.
The fixed analytical gates are declared before running any cases.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python.spike_core.cfd_tetra_mesh import admit_cfd_tetra_mesh, prepare_cfd_tetra_mesh
from python.spike_core.cfd_tetra_stokes import solve_cfd_tetra_stokes
from python.spike_core.cfd_tetra_energy import solve_cfd_tetra_energy
from python.spike_core.gmsh_occ_runtime import run_occ_case

SIZES_MM = (.5, .35, .25, .18)
GATES = {"quadratic_finest_relative_velocity_l2": .05,
         "analytic_cad_relative_volume_error": 1e-10,
         "quadratic_minimum_endpoint_order": .8,
         "affine_relative_velocity_l2": 1e-8,
         "affine_normalized_pressure_l2": 1e-7,
         "signed_enthalpy_transfer_relative_error": 1e-10,
         "uniform_enthalpy_maximum_temperature_error_k": 1e-8}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def patches(occ, fixture):
    vertices = np.asarray(occ["mesh"]["vertices"])
    grouped = {}
    for face in occ["boundary_faces"]:
        grouped.setdefault(face["cad_surface_tag"], []).append(face["vertices"])
    labels = {}
    for tag, faces in grouped.items():
        points = vertices[np.asarray(faces)].reshape(-1, 3)
        axial = points[:, 0]-(.25*points[:, 1] if fixture == "sheared_duct" else 0.)
        labels[tag] = ("inlet" if np.max(np.abs(axial)) < 1e-8 else
                       "outlet" if np.max(np.abs(axial-2.)) < 1e-8 else "prescribed_sides")
    if set(labels.values()) != {"inlet", "outlet", "prescribed_sides"}:
        raise ValueError("Fixture surface classification is incomplete")
    return labels


def flow_request(mesh, affine):
    admitted = admit_cfd_tetra_mesh(mesh)
    vertices = admitted["vertices"]
    conditions = {}
    for name, faces in admitted["boundary_patches"].items():
        y = vertices[admitted["face_vertices"][faces]][:, :, 1]
        mean = y.mean(axis=1)
        velocity = np.zeros((len(faces), 3))
        velocity[:, 0] = (1e-4+.1*mean if affine else
                          400*(.001*mean-(np.sum(y*y, axis=1)+np.sum(y, axis=1)**2)/12))
        if name == "outlet":
            traction = np.zeros_like(velocity)
            gradient = np.full(len(faces), .1) if affine else 400*(.001-2*mean)
            traction[:, 0] = gradient*admitted["face_normals"][faces, 1]
            conditions[name] = {"kind": "pseudo_traction",
                                "face_average_pseudo_traction_pa": traction.tolist(),
                                "reject_backflow": True}
        else:
            conditions[name] = {"kind": "velocity_dirichlet",
                                "face_average_velocity_m_s": velocity.tolist()}
    force = np.zeros((len(mesh["cells"]), 3))
    if not affine:
        force[:, 0] = 800.
    return {"contract": "spike/cfd-tetra-stokes/v1", "mesh": mesh,
            "dynamic_viscosity_pa_s": 1., "density_kg_m3": 1.,
            "body_force_n_m3": force.tolist(), "boundary_conditions": conditions,
            "controls": {"max_runtime_s": 60.}}


def quadrature():
    node, weight = np.polynomial.legendre.leggauss(4)
    node, weight = (node+1)/2, weight/2
    bary, weights = [], []
    for i, j, k in itertools.product(range(4), repeat=3):
        a, b, c = node[i], node[j], node[k]
        bary.append([(1-a)*(1-b)*(1-c), a, (1-a)*b, (1-a)*(1-b)*c])
        weights.append(6*weight[i]*weight[j]*weight[k]*(1-a)**2*(1-b))
    return np.asarray(bary), np.asarray(weights)


def errors(mesh, result, affine):
    geometry = admit_cfd_tetra_mesh(mesh)
    bary, weights = quadrature()
    xyz = np.einsum("qj,cjd->cqd", bary, geometry["vertices"][geometry["cells"]])
    fields = result["fields"]
    face_u = np.asarray(fields["face_average_velocity_m_s"])
    actual = np.einsum("qj,cjd->cqd", 1-3*np.asarray(bary), face_u[geometry["cell_faces"]])
    exact = np.zeros_like(actual)
    y = xyz[:, :, 1]
    exact[:, :, 0] = 1e-4+.1*y if affine else 400*y*(.001-y)
    measure = geometry["cell_volumes"][:, None]*weights
    relative = np.sqrt(np.sum(measure*np.sum((actual-exact)**2, axis=2)) /
                       np.sum(measure*np.sum(exact**2, axis=2)))
    pressure = np.asarray(fields["cell_pressure_pa"])
    p_norm = np.sqrt(np.average(pressure**2, weights=geometry["cell_volumes"]))/.05
    return {"relative_velocity_l2": float(relative), "normalized_pressure_l2": float(p_norm),
            "effective_h_m": float((sum(geometry["cell_volumes"])/len(mesh["cells"]))**(1/3))}


def enthalpy_case(mesh, flow_result, directory):
    """Same-topology shared mass flux, not a turbulent heat-transfer closure."""
    geometry = admit_cfd_tetra_mesh(mesh)
    velocity = np.asarray(flow_result["fields"]["face_average_velocity_m_s"])
    mass = geometry["face_areas"]*np.einsum("fd,fd->f", velocity, geometry["face_normals"])
    request = {"contract": "spike/cfd-tetra-energy/v1", "mesh": mesh,
               "cell_material_ids": ["fluid"]*len(mesh["cells"]),
               "materials": {"fluid": {"phase": "fluid", "conductivity_w_mk": .6,
                                       "specific_heat_j_kgk": 1000.}},
               "face_mass_flow_kg_s": mass.tolist(), "source_w_m3": [0.]*len(mesh["cells"]),
               "reference_temperature_k": 300.,
               "boundaries": {name: {"type": "temperature", "temperature_k": 350.}
                              for name in mesh["boundary_patches"]}}
    save(directory/"energy-request.json", request)
    result = solve_cfd_tetra_energy(request)
    save(directory/"energy-result.json", result)
    if result.get("status") != "completed":
        raise ValueError("Energy blocked: "+json.dumps(result.get("issues", [])))
    error = float(np.max(np.abs(np.asarray(result["fields"]["temperature_k"])-350.)))
    if error > GATES["uniform_enthalpy_maximum_temperature_error_k"]:
        raise ValueError("Uniform enthalpy temperature error exceeds fixed 1e-8 K gate")
    flow_patches = flow_result["diagnostics"]["boundary_patch_outward_flux_m3_s"]
    expected = {name: value*1000.*350. for name, value in flow_patches.items()}
    advective = np.asarray(result["fields"]["face_advective_heat_flow_w"])
    actual = {name: math.fsum(float(advective[f]) for f in faces)
              for name, faces in geometry["boundary_patches"].items()}
    scale = math.fsum(abs(value) for value in expected.values())
    transfer = max(abs(actual[name]-value) for name, value in expected.items())/scale
    if (flow_patches["inlet"] >= 0. or flow_patches["outlet"] <= 0. or
            transfer > GATES["signed_enthalpy_transfer_relative_error"]):
        raise ValueError("Signed source-flow to thermal-enthalpy transfer failed fixed 1e-10 gate")
    return {"maximum_temperature_error_k": error, "diagnostics": result["diagnostics"],
            "expected_outward_patch_enthalpy_w": expected, "actual_outward_patch_enthalpy_w": actual,
            "signed_enthalpy_transfer_relative_error": transfer,
            "scope": "constant-temperature preservation using actual solved mass flux; not heated CHT validation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="+", choices=["box", "sheared_duct", "cylinder"],
                        default=["box", "sheared_duct", "cylinder"])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    fixture_manifest = json.loads((args.fixtures/"manifest.json").read_text(encoding="utf-8"))
    if (fixture_manifest.get("contract") != "spike/cfd-step-fixtures/v1" or
            fixture_manifest.get("generator_sha256") != digest(ROOT/"scripts/generate_cfd_step_fixtures.py") or
            any(fixture_manifest["fixtures"][name]["sha256"] != digest(args.fixtures/(name+".step"))
                for name in args.cases)):
        raise ValueError("Fixture manifest/source/input digest mismatch; regenerate fixtures")
    sources = [Path(__file__), ROOT/"scripts/generate_cfd_step_fixtures.py"]
    sources += [ROOT/"python/spike_core"/name for name in (
        "cfd_tetra_mesh.py", "cfd_tetra_intersections.py", "cfd_tetra_stokes.py", "cfd_tetra_energy.py",
        "gmsh_occ_runtime.py", "gmsh_occ_mesher.py", "enclosure_sa_transport.py",
        "tetra_mesh_refinement.py", "assembly_thermal_cad.py",
        "assembly_thermal_encapsulation_occ.py", "assembly_frames.py",
        "assembly_field_handoff.py", "gmsh_environment.py")]
    report = {"contract": "spike/cad-cfd-benchmark/v1", "gates": GATES,
              "fixture_manifest_sha256": digest(args.fixtures/"manifest.json"),
              "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sources},
              "cases": [], "production_qualified": False,
              "scope": "single-solid STEP; prescribed manufactured boundaries; creeping vector-Laplacian Stokes"}
    passed = True
    for fixture in args.cases:
        rows = []
        sizes = SIZES_MM if fixture != "cylinder" else (.25,)
        for size in sizes:
            case = args.output/f"{fixture}-{size}"
            case.mkdir()
            row = {"fixture": fixture, "target_size_mm": size}
            try:
                step = (args.fixtures/(fixture+".step")).resolve()
                request = {"contract": "spike/gmsh-occ-step/v1", "solids": [{
                    "id": "fluid-domain", "material_id": "reference-fluid", "priority": 0,
                    "shape": {"kind": "step_solid", "path": str(step), "sha256": digest(step),
                              "transform": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}}],
                    "mesh": {"min_size_mm": size, "max_size_mm": size,
                             "max_cells": 4096, "max_vertices": 4096}}
                run_occ_case(request, case/"occ", timeout_s=60, memory_limit_mb=2048)
                occ = json.loads((case/"occ/result.json").read_text(encoding="utf-8"))
                analytic_volume = float(np.pi/2) if fixture == "cylinder" else 1.
                cad_volume_error = abs(occ["metrics"]["cad_volume_mm3"]-analytic_volume)/analytic_volume
                row["analytic_cad_relative_volume_error"] = cad_volume_error
                if cad_volume_error > GATES["analytic_cad_relative_volume_error"]:
                    raise ValueError("Analytic CAD volume differs by more than fixed 1e-10 relative gate")
                bridge = prepare_cfd_tetra_mesh(occ, patches(occ, fixture))
                save(case/"bridge.json", bridge)
                flow = flow_request(bridge["mesh"], fixture == "cylinder")
                save(case/"flow-request.json", flow)
                result = solve_cfd_tetra_stokes(flow)
                save(case/"flow-result.json", result)
                if result.get("status") != "completed":
                    raise ValueError("Flow blocked: "+json.dumps(result.get("issues", [])))
                row.update(errors(bridge["mesh"], result, fixture == "cylinder"))
                row["enthalpy"] = enthalpy_case(bridge["mesh"], result, case)
                row.update(tetrahedra=len(bridge["mesh"]["cells"]), status="completed",
                           geometry=bridge["geometry_diagnostics"])
            except Exception as exc:
                row.update(status="failed", error_type=type(exc).__name__, error=str(exc))
                passed = False
            rows.append(row)
            print(json.dumps(row), flush=True)
            report["cases"].append(row)
            save(args.output/"report.json", report)
        if all(r["status"] == "completed" for r in rows):
            if fixture == "cylinder":
                accepted = rows[0]["relative_velocity_l2"] <= GATES["affine_relative_velocity_l2"] and rows[0]["normalized_pressure_l2"] <= GATES["affine_normalized_pressure_l2"]
            else:
                order = float(np.log(rows[-1]["relative_velocity_l2"]/rows[0]["relative_velocity_l2"])/
                              np.log(rows[-1]["effective_h_m"]/rows[0]["effective_h_m"]))
                report.setdefault("endpoint_orders", {})[fixture] = order
                accepted = rows[-1]["relative_velocity_l2"] <= .05 and order >= .8
            passed = passed and accepted
    report["numerical_gates_passed"] = passed
    report["sources_unchanged"] = all(digest(ROOT/p) == h for p, h in report["source_sha256"].items())
    report["passed"] = passed and report["sources_unchanged"]
    report["artifact_sha256"] = {str(p.relative_to(args.output)): digest(p)
                                 for p in sorted(args.output.rglob("*"))
                                 if p.is_file() and p != args.output/"report.json"}
    save(args.output/"report.json", report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
