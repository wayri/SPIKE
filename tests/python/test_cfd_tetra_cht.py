# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Independent composition, identity, conservation and refinement checks."""
import copy
import hashlib
import itertools
import json
import math
import unittest

import numpy as np

from python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_cht import CONTRACT, cfd_tetra_cht_capabilities, solve_cfd_tetra_cht
from python.spike_core.solvers.thermal_fluid.flow.cfd_tetra_mesh import CfdTetraMeshError, _admit_with_reuse, _raw_mesh_encoding, _resolve_admission, admit_cfd_tetra_mesh
from python.spike_core.multiboard_identity import canonical_json_digest


def two_phase_mesh(n):
    shape = (2*n, n, n)
    nodes = list(itertools.product(*(range(value+1) for value in shape)))
    ids = {node: index for index, node in enumerate(nodes)}
    vertices = np.asarray(nodes, dtype=float)/np.asarray(shape)
    cells = []
    for base in itertools.product(*(range(value) for value in shape)):
        for order in itertools.permutations(range(3)):
            position = list(base)
            cell = [ids[tuple(position)]]
            for axis in order:
                position[axis] += 1
                cell.append(ids[tuple(position)])
            if np.linalg.det((vertices[cell[1:]]-vertices[cell[0]]).T) < 0.:
                cell[0], cell[1] = cell[1], cell[0]
            cells.append(cell)
    owners = {}
    for cell in cells:
        for triangle in itertools.combinations(cell, 3):
            key = tuple(sorted(triangle))
            owners[key] = owners.get(key, 0)+1
    patches = {name: [] for name in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")}
    for triangle, count in owners.items():
        if count != 1:
            continue
        points = vertices[list(triangle)]
        for axis, low, high in ((0, "xmin", "xmax"), (1, "ymin", "ymax"), (2, "zmin", "zmax")):
            if np.all(points[:, axis] == 0.):
                patches[low].append(list(triangle))
                break
            if np.all(points[:, axis] == 1.):
                patches[high].append(list(triangle))
                break
    return {"contract": "spike/cfd-tetra-mesh/v1", "units": "m",
            "vertices": vertices.tolist(), "cells": cells, "boundary_patches": patches}


def affine_two_phase_request(n):
    mesh = two_phase_mesh(n)
    geometry = admit_cfd_tetra_mesh(mesh)
    fluid = geometry["cell_centroids"][:, 0] > .5
    material_ids = ["fluid" if value else "solid" for value in fluid]
    amplitude, temperature_gradient, density, cp = .005, 10., 1., 100.
    velocity_y = amplitude*(geometry["cell_centroids"][:, 0]-.5)
    source = np.where(fluid, density*cp*velocity_y*temperature_gradient, 0.)
    flow_boundaries = {}
    vertices = np.asarray(mesh["vertices"])
    for name, triangles in mesh["boundary_patches"].items():
        retained = []
        for triangle in triangles:
            points = vertices[triangle]
            if np.mean(points[:, 0]) >= .5:
                value = [0., amplitude*(np.mean(points[:, 0])-.5), 0.]
                retained.append(value)
        if retained:
            flow_boundaries[name] = {
                "kind": "velocity_dirichlet", "face_average_velocity_m_s": retained}
    thermal_boundaries = {}
    for name, triangles in mesh["boundary_patches"].items():
        face_temperature = [300.+temperature_gradient*np.mean(vertices[triangle, 1])
                            for triangle in triangles]
        thermal_boundaries[name] = {"type": "temperature", "temperature_k": face_temperature}
    return {
        "contract": CONTRACT,
        "mesh": mesh,
        "identity": {"source_id": f"independent-affine-two-phase-n{n}",
                     "source_sha256": "1"*64,
                     "mesh_sha256": canonical_json_digest(mesh)},
        "flow": {"dynamic_viscosity_pa_s": 1., "density_kg_m3": density,
                 "body_force_n_m3": np.zeros((len(mesh["cells"]), 3)).tolist(),
                 "boundary_conditions": flow_boundaries, "controls": {}},
        "energy": {"cell_material_ids": material_ids,
                   "materials": {
                       "solid": {"phase": "solid", "conductivity_w_mk": 2.,
                                 "specific_heat_j_kgk": 0.},
                       "fluid": {"phase": "fluid", "conductivity_w_mk": 1.,
                                 "specific_heat_j_kgk": cp}},
                   "source_w_m3": source.tolist(), "reference_temperature_k": 300.,
                   "boundaries": thermal_boundaries},
    }, geometry


class TetraChtCompositionTests(unittest.TestCase):
    def solve(self, request):
        result = solve_cfd_tetra_cht(request)
        self.assertEqual(result.get("status"), "completed", result)
        self.assertTrue(result["research_only"])
        self.assertFalse(result["production_qualified"])
        return result

    def test_capabilities_identity_mapping_and_solid_mask(self):
        request, geometry = affine_two_phase_request(1)
        result = self.solve(request)
        capabilities = cfd_tetra_cht_capabilities()
        self.assertFalse(capabilities["inertia"])
        self.assertFalse(capabilities["turbulence"])
        self.assertFalse(capabilities["general_cad_import"])
        self.assertFalse(capabilities["production_qualified"])
        self.assertEqual(result["provenance"]["source_id"], request["identity"]["source_id"])
        self.assertEqual(result["provenance"]["source_sha256"], "1"*64)
        self.assertEqual(result["provenance"]["mesh_sha256"], canonical_json_digest(request["mesh"]))
        self.assertFalse(result["provenance"]["source_authenticity_verified"])
        fields = result["fields"]
        fluid = np.asarray(fields["fluid_cell_mask"])
        mass = np.asarray(fields["face_mass_flow_kg_s"])
        self.assertTrue(np.any(abs(mass) > 0.))
        for face, (left, right) in enumerate(geometry["face_owners"]):
            if not fluid[left] or (right >= 0 and not fluid[right]):
                self.assertEqual(mass[face], 0.)
        self.assertLessEqual(result["diagnostics"]["coupling"]
                             ["maximum_fluid_cell_mass_relative_defect"], 1e-10)
        self.assertEqual(result["diagnostics"]["coupling"]
                         ["maximum_solid_incident_mass_flow_kg_s"], 0.)
        self.assertLessEqual(abs(result["diagnostics"]["coupling"]
                                 ["global_exterior_mass_imbalance_kg_s"]), 1e-15)
        self.assertLessEqual(result["diagnostics"]["energy"]["global_energy_relative_defect"], 1e-9)

        full_vertices = geometry["face_vertices"]
        sub_vertices = np.asarray(fields["flow"]["face_vertices"])
        vertex_map = np.asarray(fields["fluid_submesh_vertex_to_retained_vertex"])
        face_map = np.asarray(fields["fluid_submesh_face_to_retained_face"])
        for local, retained in enumerate(face_map):
            self.assertEqual(set(vertex_map[sub_vertices[local]]), set(full_vertices[retained]))

    def test_composition_admits_each_distinct_mesh_once(self):
        request, _ = affine_two_phase_request(2)
        from unittest.mock import patch
        from python.spike_core.solvers.thermal_fluid.flow import cfd_tetra_cht
        original = cfd_tetra_cht._admit_with_reuse
        calls = []
        def counted(mesh, *args, **kwargs):
            calls.append(mesh)
            return original(mesh, *args, **kwargs)
        with patch.object(cfd_tetra_cht, "_admit_with_reuse", side_effect=counted):
            result = solve_cfd_tetra_cht(request)
        self.assertEqual(result["status"], "completed", result)
        self.assertEqual(len(calls), 2)
        self.assertIs(calls[0], request["mesh"])
        self.assertIsNot(calls[1], request["mesh"])

    def test_reuse_rejects_nested_mutation_from_cancellation_callback(self):
        request, _ = affine_two_phase_request(1)
        raw = request["mesh"]
        admitted, ticket = _admit_with_reuse(raw)
        original = raw["vertices"][0][0]
        def mutate_and_continue():
            raw["vertices"][0][0] = original + .125
            return False
        with self.assertRaisesRegex(CfdTetraMeshError, "changed after admission"):
            _resolve_admission(raw, ticket, mutate_and_continue)

    def test_admission_snapshot_resists_callback_aba_mutation(self):
        request, _ = affine_two_phase_request(1)
        raw = request["mesh"]
        pristine = copy.deepcopy(raw["vertices"])
        calls = 0
        def translate_then_restore():
            nonlocal calls
            calls += 1
            if calls == 1:
                for vertex in raw["vertices"]:
                    vertex[0] += .25
            elif calls == 2:
                raw["vertices"][:] = copy.deepcopy(pristine)
            return False
        admitted, ticket = _admit_with_reuse(raw, translate_then_restore)
        self.assertGreaterEqual(calls, 2)
        self.assertEqual(raw["vertices"], pristine)
        np.testing.assert_array_equal(admitted["vertices"], np.asarray(pristine))
        self.assertEqual(list(admitted["boundary_patches"]),
                         list(raw["boundary_patches"]))
        self.assertIs(_resolve_admission(raw, ticket, None), admitted)

    def test_reuse_digest_does_not_normalize_tuple_into_list(self):
        request, _ = affine_two_phase_request(1)
        raw = request["mesh"]
        admitted, ticket = _admit_with_reuse(raw)
        raw["cells"][0] = tuple(raw["cells"][0])
        with self.assertRaisesRegex(CfdTetraMeshError, "plain JSON containers"):
            _resolve_admission(raw, ticket, None)
        with self.assertRaisesRegex(CfdTetraMeshError, "plain JSON containers"):
            _admit_with_reuse(raw)

    def test_reuse_digest_detects_mapping_order_change(self):
        request, _ = affine_two_phase_request(1)
        raw = request["mesh"]
        _, ticket = _admit_with_reuse(raw)
        patches = raw["boundary_patches"]
        first = next(iter(patches))
        patches[first] = patches.pop(first)
        with self.assertRaisesRegex(CfdTetraMeshError, "changed after admission"):
            _resolve_admission(raw, ticket, None)

    def test_reuse_encoding_preserves_reviewed_json_bytes_and_snapshot(self):
        raw = {"unicode": "PCB \x7f Ω \U0001f680", "values": [-0.0, 1e-7, True, None],
               "ordered": {"z": 1, "a": 2}}
        encoded = json.dumps(
            raw, sort_keys=False, allow_nan=False, separators=(",", ":"))
        digest, snapshot = _raw_mesh_encoding(raw, retain=True)
        self.assertEqual(digest, hashlib.sha256(encoded.encode("utf-8")).hexdigest())
        self.assertEqual(snapshot, json.loads(encoded))
        self.assertEqual(list(snapshot["ordered"]), ["z", "a"])

    def test_retained_reuse_rejects_mutation_during_flow_stage(self):
        request, _ = affine_two_phase_request(1)
        from unittest.mock import patch
        from python.spike_core.solvers.thermal_fluid.flow import cfd_tetra_cht
        original = cfd_tetra_cht.solve_cfd_tetra_stokes
        mutated = False
        def solve_with_mutating_callback(flow_request, *, cancel_check=None, _mesh_reuse=None):
            def mutate_full_mesh_and_continue():
                nonlocal mutated
                if not mutated:
                    request["mesh"]["cells"][0][0] = request["mesh"]["cells"][0][1]
                    mutated = True
                return False
            return original(flow_request, cancel_check=mutate_full_mesh_and_continue,
                            _mesh_reuse=_mesh_reuse)
        with patch.object(cfd_tetra_cht, "solve_cfd_tetra_stokes",
                          side_effect=solve_with_mutating_callback):
            result = solve_cfd_tetra_cht(request)
        self.assertTrue(mutated)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("changed after admission", result["issues"][0]["message"])
        self.assertNotIn("fields", result)

    def test_affine_flow_is_exact_and_coupled_energy_converges(self):
        errors = []
        for n in (1, 2, 4):
            request, geometry = affine_two_phase_request(n)
            result = self.solve(request)
            fields = result["fields"]
            vertex_map = np.asarray(fields["fluid_submesh_vertex_to_retained_vertex"])
            sub_faces = np.asarray(fields["flow"]["face_vertices"])
            centers = geometry["vertices"][vertex_map[sub_faces]].mean(axis=1)
            expected_velocity = np.zeros((len(centers), 3))
            expected_velocity[:, 1] = .005*(centers[:, 0]-.5)
            np.testing.assert_allclose(fields["flow"]["face_average_velocity_m_s"],
                                       expected_velocity, rtol=0., atol=2e-15)
            temperature = np.asarray(fields["energy"]["temperature_k"])
            exact = 300.+10.*geometry["cell_centroids"][:, 1]
            volume = geometry["cell_volumes"]
            error = math.sqrt(float(np.sum(volume*(temperature-exact)**2)/np.sum(volume)))
            errors.append(error)
            self.assertLessEqual(result["diagnostics"]["flow"]["maximum_local_mass_scaled_residual"], 1e-10)
            self.assertLessEqual(result["diagnostics"]["energy"]["cell_energy_relative_defect"], 1e-9)
        self.assertLess(errors[1], .7*errors[0], errors)
        self.assertLess(errors[2], .7*errors[1], errors)
        self.assertGreater(math.log(errors[0]/errors[1], 2.), .5)
        self.assertGreater(math.log(errors[1]/errors[2], 2.), .5)

    def test_identity_solid_force_and_stage_failures_publish_no_fields(self):
        base, _ = affine_two_phase_request(1)
        mutations = []
        wrong_identity = copy.deepcopy(base)
        wrong_identity["identity"]["mesh_sha256"] = "0"*64
        mutations.append(wrong_identity)
        solid_force = copy.deepcopy(base)
        solid = solid_force["energy"]["cell_material_ids"].index("solid")
        solid_force["flow"]["body_force_n_m3"][solid][0] = 1.
        mutations.append(solid_force)
        bad_energy = copy.deepcopy(base)
        bad_energy["energy"]["boundaries"].pop("xmin")
        mutations.append(bad_energy)
        for request in mutations:
            result = solve_cfd_tetra_cht(request)
            self.assertEqual(result["status"], "blocked", result)
            self.assertNotIn("fields", result)
            self.assertNotIn("diagnostics", result)
            self.assertNotIn("provenance", result)

        cancelled = solve_cfd_tetra_cht(base, cancel_check=lambda: True)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertNotIn("fields", cancelled)


if __name__ == "__main__":
    unittest.main()
