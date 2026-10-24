# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Probe bounded tetra CFD/CHT through a source or frozen JSON-line worker.

The two-tetrahedron fixture is an independently authored packaging oracle.  It
checks installation, routing, identity and conservative field transfer; it is
not physical engineering validation or general CAD/CHT qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REQUEST_CONTRACT = "spike/cfd-tetra-cht/v1"
RESULT_CONTRACT = "spike/cfd-tetra-cht-result/v1"


def _canonical_numbers(value):
    if isinstance(value, dict):
        return {key: _canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_numbers(item) for item in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _digest(value):
    encoded = json.dumps(_canonical_numbers(value), sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def probe_request():
    """Return a tiny nonzero-flow, two-phase, constant-temperature oracle."""
    # Two positively oriented tetrahedra share x=0.  The fluid is at x>=0,
    # the solid at x<=0.  u=(0, 1e-3*x, 0) is affine, divergence-free,
    # harmonic and exactly zero at the stationary fluid-solid interface.
    vertices = [[0, 0, 0], [0, 1, 0], [0, 0, 1], [1, 0, 0], [-1, 0, 0]]
    mesh = {
        "contract": "spike/cfd-tetra-mesh/v1",
        "units": "m",
        "vertices": vertices,
        "cells": [[0, 3, 1, 2], [0, 1, 4, 2]],
        "boundary_patches": {
            "fluid_external": [[3, 1, 2], [0, 3, 2], [0, 1, 3]],
            "solid_external": [[1, 4, 2], [0, 2, 4], [0, 1, 4]],
        },
    }
    speed_gradient = 1e-3
    fluid_face_velocity = [
        [0., speed_gradient*sum(vertices[index][0] for index in triangle)/3., 0.]
        for triangle in mesh["boundary_patches"]["fluid_external"]
    ]
    return {
        "contract": REQUEST_CONTRACT,
        "mesh": mesh,
        "identity": {
            "source_id": "independent-two-tetra-packaging-oracle",
            "source_sha256": hashlib.sha256(b"SPIKE tetra CHT packaging oracle v1").hexdigest(),
            "mesh_sha256": _digest(mesh),
        },
        "flow": {
            "dynamic_viscosity_pa_s": 1.,
            "density_kg_m3": 1.,
            "body_force_n_m3": [[0., 0., 0.], [0., 0., 0.]],
            "boundary_conditions": {"fluid_external": {
                "kind": "velocity_dirichlet",
                "face_average_velocity_m_s": fluid_face_velocity,
            }},
            "controls": {"max_runtime_s": 30.},
        },
        "energy": {
            "cell_material_ids": ["fluid", "solid"],
            "materials": {
                "fluid": {"phase": "fluid", "conductivity_w_mk": 1.,
                          "specific_heat_j_kgk": 1000.},
                "solid": {"phase": "solid", "conductivity_w_mk": 2.,
                          "specific_heat_j_kgk": 0.},
            },
            "source_w_m3": [0., 0.],
            "reference_temperature_k": 300.,
            "boundaries": {
                "fluid_external": {"type": "temperature", "temperature_k": 310.},
                "solid_external": {"type": "temperature", "temperature_k": 310.},
            },
        },
    }


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def verify_tetra_cht_runtime(executable, request):
    """Exercise and certify the installed service route using ``request``."""
    catalog_response = request(executable, "cfd_capabilities", {})
    _require(catalog_response.get("ok") is True, "Packaged CFD catalog request failed")
    engine = catalog_response.get("result", {}).get("engines", {}).get("spike.tetra_cht", {})
    _require(engine.get("available") is True
             and engine.get("request_contract") == REQUEST_CONTRACT
             and engine.get("result_contract") == RESULT_CONTRACT,
             "Packaged tetra CHT capability is absent or incompatible")
    for unsupported in ("inertia", "turbulence", "buoyancy_feedback",
                        "general_cad_import", "production_qualified"):
        _require(engine.get(unsupported) is False,
                 f"Packaged tetra CHT incorrectly advertises {unsupported}")

    oracle = probe_request()
    response = request(executable, "run_cfd_tetra_cht", {"request": oracle})
    _require(response.get("ok") is True, "Packaged tetra CHT service call failed")
    result = response.get("result", {})
    _require(result.get("contract") == RESULT_CONTRACT and result.get("status") == "completed",
             f"Packaged tetra CHT did not complete: {result}")
    _require(result.get("model_status") == "experimental"
             and result.get("research_only") is True
             and result.get("production_qualified") is False,
             "Packaged tetra CHT status was incorrectly promoted")
    provenance = result.get("provenance", {})
    _require(provenance.get("source_id") == oracle["identity"]["source_id"]
             and provenance.get("source_sha256") == oracle["identity"]["source_sha256"]
             and provenance.get("mesh_sha256") == oracle["identity"]["mesh_sha256"]
             and provenance.get("request_sha256") == _digest(oracle)
             and provenance.get("source_authenticity_verified") is False,
             "Packaged tetra CHT dropped or altered retained identity")

    fields = result.get("fields", {})
    _require(fields.get("fluid_cell_mask") == [True, False],
             "Packaged tetra CHT changed the explicit solid mask")
    mass = fields.get("face_mass_flow_kg_s", [])
    _require(isinstance(mass, list) and len(mass) == 7
             and all(isinstance(value, (int, float)) and math.isfinite(value) for value in mass)
             and max(abs(value) for value in mass) > 1e-6,
             "Packaged tetra CHT did not retain finite nonzero mass flow")
    flow_fields = fields.get("flow", {})
    face_map = fields.get("fluid_submesh_face_to_retained_face", [])
    vertex_map = fields.get("fluid_submesh_vertex_to_retained_vertex", [])
    sub_faces = flow_fields.get("face_vertices", [])
    velocity = flow_fields.get("face_average_velocity_m_s", [])
    _require(len(face_map) == len(sub_faces) == len(velocity) == 4,
             "Packaged tetra CHT fluid-face maps are incomplete")
    interface_face = None
    for local, face in enumerate(sub_faces):
        retained_vertices = {vertex_map[index] for index in face}
        expected = 1e-3*sum(oracle["mesh"]["vertices"][index][0]
                            for index in retained_vertices)/3.
        actual = velocity[local]
        _require(len(actual) == 3 and math.isclose(actual[0], 0., abs_tol=2e-15)
                 and math.isclose(actual[1], expected, abs_tol=2e-15)
                 and math.isclose(actual[2], 0., abs_tol=2e-15),
                 "Packaged tetra CHT changed the affine face velocity oracle")
        if retained_vertices == {0, 1, 2}:
            interface_face = face_map[local]
    _require(interface_face is not None and mass[interface_face] == 0.,
             "Packaged tetra CHT violated stationary solid-interface masking")
    active = set(face_map)
    _require(all(value == 0. for index, value in enumerate(mass) if index not in active),
             "Packaged tetra CHT published mass flow on a solid-only face")

    gradients = flow_fields.get("cell_velocity_gradient_s_inv", [])
    _require(len(gradients) == 1 and len(gradients[0]) == 3
             and math.isclose(gradients[0][1][0], 1e-3, rel_tol=0., abs_tol=2e-15)
             and math.isclose(sum(abs(value) for row in gradients[0] for value in row),
                              1e-3, rel_tol=0., abs_tol=2e-15),
             "Packaged tetra CHT changed the affine velocity-gradient oracle")
    temperatures = fields.get("energy", {}).get("temperature_k", [])
    _require(len(temperatures) == 2
             and all(math.isclose(value, 310., rel_tol=0., abs_tol=1e-10)
                     for value in temperatures),
             "Packaged tetra CHT changed the constant-temperature oracle")
    advective = fields.get("energy", {}).get("face_advective_heat_flow_w", [])
    _require(advective and max(abs(value) for value in advective) > 1.,
             "Packaged tetra CHT energy stage did not retain nonzero enthalpy flow")

    diagnostics = result.get("diagnostics", {})
    coupling = diagnostics.get("coupling", {})
    flow = diagnostics.get("flow", {})
    energy = diagnostics.get("energy", {})
    _require(coupling.get("fluid_cells") == 1 and coupling.get("solid_cells") == 1
             and coupling.get("maximum_solid_incident_mass_flow_kg_s") == 0.
             and coupling.get("maximum_fluid_cell_mass_relative_defect", math.inf) <= 1e-10
             and abs(coupling.get("global_exterior_mass_imbalance_kg_s", math.inf)) <= 1e-12,
             "Packaged tetra CHT coupling conservation certificate failed")
    _require(flow.get("maximum_local_mass_scaled_residual", math.inf) <= 1e-10
             and flow.get("relative_energy_defect", math.inf) <= 1e-9,
             "Packaged tetra flow certificate failed")
    _require(energy.get("mass_relative_defect", math.inf) <= 1e-10
             and energy.get("cell_energy_relative_defect", math.inf) <= 1e-9
             and energy.get("global_energy_relative_defect", math.inf) <= 1e-9,
             "Packaged tetra energy certificate failed")
    return {
        "status": "passed",
        "production_qualified": False,
        "method": "run_cfd_tetra_cht",
        "request_contract": REQUEST_CONTRACT,
        "result_contract": RESULT_CONTRACT,
        "retained_cells": coupling["retained_cells"],
        "fluid_cells": coupling["fluid_cells"],
        "solid_cells": coupling["solid_cells"],
        "maximum_mass_relative_defect": coupling["maximum_fluid_cell_mass_relative_defect"],
        "cell_energy_relative_defect": energy["cell_energy_relative_defect"],
        "global_energy_relative_defect": energy["global_energy_relative_defect"],
        "temperature_k": temperatures,
        "scope": "Synthetic two-tetra packaging oracle; not general CAD or engineering CHT validation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path,
                        help="Frozen worker executable; omit to probe the source service")
    parser.add_argument("--output", type=Path,
                        help="Create this JSON report path exclusively")
    args = parser.parse_args()

    def request(executable, method, params):
        command = [str(executable)] if executable else [sys.executable, "-m", "python.spike_core.service"]
        process = subprocess.run(
            command,
            input=json.dumps({"id": "tetra-cht-runtime-probe", "method": method,
                              "params": params}, allow_nan=False)+"\n",
            text=True,
            capture_output=True,
            cwd=ROOT,
            timeout=120,
            check=True,
        )
        lines = [line for line in process.stdout.splitlines() if line.strip()]
        if len(lines) != 1:
            raise RuntimeError(f"Worker returned {len(lines)} JSON lines; stderr={process.stderr!r}")
        response = json.loads(lines[0])
        if response.get("ok") is not True:
            raise RuntimeError(f"Worker request failed: {response}")
        return response

    report = verify_tetra_cht_runtime(args.worker, request)
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
    print(json.dumps(report, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
