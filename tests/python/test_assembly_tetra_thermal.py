# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original analytical/manufactured fixtures; no imported mesh or solver oracle."""
import copy
import itertools
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.solvers.thermal_fluid.heat.assembly_tetra_thermal import AssemblyTetraThermalError, run_assembly_tetra_thermal


def cube(n=1, origin=0, owner="solid", unit="m"):
    vertices = [[origin + i / n, j / n, k / n]
                for i in range(n + 1) for j in range(n + 1) for k in range(n + 1)]
    index = lambda p: (p[0] * (n + 1) + p[1]) * (n + 1) + p[2]
    cells = []
    for start in itertools.product(range(n), repeat=3):
        for permutation in itertools.permutations(range(3)):
            p, nodes = list(start), [index(start)]
            for axis in permutation:
                p[axis] += 1
                nodes.append(index(p))
            xyz = np.array([vertices[i] for i in nodes])
            if np.linalg.det((xyz[1:] - xyz[0]).T) < 0:
                nodes[1], nodes[2] = nodes[2], nodes[1]
            cells.append({"id": f"{owner}-{len(cells)}", "kind": "tetrahedron", "vertices": nodes,
                          "material_id": "k", "source_object_ids": [owner]})
    return {"contract": "spike/solver-mesh/v1", "units": unit, "coordinate_system": "right_handed_xyz",
            "vertices": vertices, "cells": cells, "counts": {"vertices": len(vertices), "cells": len(cells)},
            "object_map": {owner: {"kind": "solid"}}}


def exterior(mesh):
    faces = {}
    for cell in mesh["cells"]:
        for face in itertools.combinations(cell["vertices"], 3):
            key = tuple(sorted(face))
            faces[key] = faces.get(key, 0) + 1
    return [list(f) for f, count in faces.items() if count == 1]


def faces_at(mesh, x):
    return [f for f in exterior(mesh) if all(mesh["vertices"][i][0] == x for i in f)]


def boundary(faces, kind, **parameters):
    return [{"id": "f-" + "-".join(map(str, f)), "vertices": f, "type": kind, **parameters} for f in faces]


def request(mesh=None):
    mesh = mesh or cube()
    return {"contract": "spike/assembly-tetra-thermal-request/v1", "mesh": mesh,
            "materials": [{"id": "k", "thermal_conductivity_w_mk": 2.0}],
            "boundaries": boundary(faces_at(mesh, 0), "temperature", temperature_k=300) +
                          boundary(faces_at(mesh, 1), "temperature", temperature_k=400)}


def contact_request():
    left, right = cube(owner="left"), cube(origin=1, owner="right")
    offset = len(left["vertices"])
    mesh = copy.deepcopy(left)
    mesh["vertices"] += right["vertices"]
    mesh["cells"] += [{**c, "vertices": [i + offset for i in c["vertices"]]} for c in right["cells"]]
    mesh["object_map"].update(right["object_map"])
    mesh["counts"] = {"vertices": len(mesh["vertices"]), "cells": len(mesh["cells"])}
    raw = request(mesh)
    raw["boundaries"] = boundary(faces_at(mesh, 0), "temperature", temperature_k=300)
    raw["boundaries"] += boundary(faces_at(mesh, 2), "temperature", temperature_k=400)
    contacts = []
    for lf in faces_at(left, 1):
        positions = {tuple(left["vertices"][i]) for i in lf}
        rf = next(f for f in faces_at(right, 1) if {tuple(right["vertices"][i]) for i in f} == positions)
        contacts.append({"id": f"contact-{len(contacts)}", "left_vertices": lf,
                         "right_vertices": [i + offset for i in reversed(rf)],
                         "thermal_contact_conductance_w_m2k": 4.})
    raw["contacts"] = contacts
    return raw


class AssemblyTetraThermalTests(unittest.TestCase):
    def test_exact_slab_and_si_conversion(self):
        raw = request(cube(2))
        before = copy.deepcopy(raw)
        out = run_assembly_tetra_thermal(raw)
        self.assertEqual(raw, before)
        expected = [300 + 100 * p[0] for p in raw["mesh"]["vertices"]]
        np.testing.assert_allclose(out["node_temperatures_k"], expected, atol=1e-8)
        np.testing.assert_allclose([f["heat_flux_w_m2"] for f in out["cell_heat_flux_w_m2"]],
                                   np.tile([-200, 0, 0], (48, 1)), atol=1e-7)
        self.assertFalse(out["production_qualified"])
        self.assertTrue(out["diagnostics"]["positive_energy_check"])
        self.assertLess(abs(out["heat_balance"]["imbalance_w"]), 1e-8)
        raw["mesh"]["units"] = "mm"
        raw["mesh"]["vertices"] = [[1000 * x for x in p] for p in raw["mesh"]["vertices"]]
        converted = run_assembly_tetra_thermal(raw)
        np.testing.assert_allclose(converted["node_temperatures_k"], expected, atol=1e-8)
        np.testing.assert_allclose(converted["cell_heat_flux_w_m2"][0]["heat_flux_w_m2"], [-200, 0, 0], atol=1e-7)

    def test_contact_temperature_jump_and_reciprocal_power(self):
        raw = contact_request()
        out = run_assembly_tetra_thermal(raw)
        expected = [300 + 40 * p[0] for p in raw["mesh"]["vertices"][:8]]
        expected += [320 + 40 * p[0] for p in raw["mesh"]["vertices"][8:]]
        np.testing.assert_allclose(out["node_temperatures_k"], expected, atol=1e-8)
        self.assertAlmostEqual(sum(c["left_to_right_heat_w"] for c in out["contacts"]), -80, places=7)
        for contact in out["contacts"]:
            self.assertAlmostEqual(contact["mean_temperature_jump_k"], -20, places=7)
        self.assertGreater(out["diagnostics"]["contact_jump_energy_w_k"], 0)

    def test_neumann_convection_sign_and_global_conservation(self):
        raw = request(cube(2))
        raw["boundaries"] = boundary(faces_at(raw["mesh"], 0), "heat_flux", heat_flux_w_m2=10)
        raw["boundaries"] += boundary(faces_at(raw["mesh"], 1), "convection",
                                      heat_transfer_coefficient_w_m2k=2, ambient_temperature_k=300)
        out = run_assembly_tetra_thermal(raw)
        np.testing.assert_allclose(out["node_temperatures_k"],
                                   [310 - 5 * p[0] for p in raw["mesh"]["vertices"]], atol=1e-7)
        self.assertAlmostEqual(out["heat_balance"]["convection_outward_w"], 10, places=7)
        self.assertAlmostEqual(out["heat_balance"]["prescribed_flux_inward_w"], 10, places=7)

    def test_isothermal_zero_power_and_uniform_source_balance(self):
        raw = request(cube(2))
        for item in raw["boundaries"]:
            item["temperature_k"] = 300
        out = run_assembly_tetra_thermal(raw)
        np.testing.assert_allclose(out["node_temperatures_k"], 300, atol=1e-8)
        raw["heat_sources_w_m3"] = {cell["id"]: 12 for cell in raw["mesh"]["cells"]}
        out = run_assembly_tetra_thermal(raw)
        self.assertAlmostEqual(out["heat_balance"]["source_w"], 12, places=9)
        self.assertAlmostEqual(out["heat_balance"]["temperature_reaction_inward_w"], -12, places=8)
        self.assertLess(abs(out["heat_balance"]["imbalance_w"]), 1e-8)

    def test_tensor_rotation_covariance(self):
        raw = request(cube(2))
        raw["materials"][0]["thermal_conductivity_w_mk"] = [[2, 0, 0], [0, 3, 0], [0, 0, 5]]
        angle = .37
        rotation = np.array([[math.cos(angle), -math.sin(angle), 0],
                             [math.sin(angle), math.cos(angle), 0], [0, 0, 1]])
        raw["mesh"]["vertices"] = (np.array(raw["mesh"]["vertices"]) @ rotation.T).tolist()
        raw["materials"][0]["thermal_conductivity_w_mk"] = (rotation @ np.diag([2, 3, 5]) @ rotation.T).tolist()
        out = run_assembly_tetra_thermal(raw)
        expected = rotation @ np.array([-200, 0, 0])
        np.testing.assert_allclose([c["heat_flux_w_m2"] for c in out["cell_heat_flux_w_m2"]],
                                   np.tile(expected, (48, 1)), atol=1e-7)

    def test_manufactured_solution_four_refinements(self):
        # T=300+sin(pi*x)sin(pi*y)sin(pi*z), k=1; q=3*pi^2*(T-300).
        # Original midpoint cell sampling is refined along with the P1 mesh.
        errors = []
        for n in (2, 3, 4, 8):
            raw = request(cube(n))
            raw["materials"][0]["thermal_conductivity_w_mk"] = 1.
            raw["boundaries"] = boundary(exterior(raw["mesh"]), "temperature", temperature_k=300)
            points = np.array(raw["mesh"]["vertices"])
            exact = lambda p: np.prod(np.sin(np.pi * p), axis=-1)
            raw["heat_sources_w_m3"] = {c["id"]: float(3 * np.pi**2 * exact(points[c["vertices"]].mean(0)))
                                       for c in raw["mesh"]["cells"]}
            out = run_assembly_tetra_thermal(raw)
            temperatures = np.array(out["node_temperatures_k"])
            error = 0.
            for c in raw["mesh"]["cells"]:
                centroid = points[c["vertices"]].mean(0)
                error += (temperatures[c["vertices"]].mean() - 300 - exact(centroid))**2 / len(raw["mesh"]["cells"])
            errors.append(math.sqrt(error))
            self.assertLess(abs(out["heat_balance"]["imbalance_w"]), 1e-8)
        self.assertTrue(all(b < a for a, b in zip(errors, errors[1:])), errors)
        self.assertLess(errors[-1], errors[0] / 8, errors)

    def test_unanchored_missing_contact_spd_and_unsupported(self):
        for change in ({"boundaries": []}, {"mode": "transient"}, {"radiation": []}, {"airflow": {}},
                       {"materials": [{"id": "k", "thermal_conductivity_w_mk": [[1, 0, 0], [0, -1, 0], [0, 0, 1]]}]}):
            with self.subTest(change=change), self.assertRaises(AssemblyTetraThermalError):
                run_assembly_tetra_thermal({**request(), **change})
        raw = contact_request()
        raw["contacts"] = []
        raw["boundaries"] = raw["boundaries"][:2]
        with self.assertRaisesRegex(AssemblyTetraThermalError, "Unanchored"):
            run_assembly_tetra_thermal(raw)

    def test_malformed_fails_before_sparse_assembly(self):
        mutations = [lambda r: r["mesh"]["vertices"][0].__setitem__(0, float("nan")),
                     lambda r: r["mesh"]["cells"][0].__setitem__("vertices", [0, 0, 1, 2]),
                     lambda r: r["boundaries"][0].__setitem__("temperature_k", True),
                     lambda r: r["boundaries"].append(copy.deepcopy(r["boundaries"][0])),
                     lambda r: r.__setitem__("heat_sources_w_m3", {"missing": 1}),
                     lambda r: r["mesh"]["vertices"].extend([[0, 0, 0]] * 10000)]
        for mutate in mutations:
            raw = request()
            mutate(raw)
            with self.subTest(mutation=mutate), patch("python.spike_core.solvers.thermal_fluid.heat.assembly_tetra_thermal.coo_matrix") as sparse:
                with self.assertRaises(AssemblyTetraThermalError):
                    run_assembly_tetra_thermal(raw)
                sparse.assert_not_called()

    def test_contact_geometric_and_reuse_failures(self):
        for mutation in (lambda r: r["contacts"][0].__setitem__("thermal_contact_conductance_w_m2k", 0),
                         lambda r: r["contacts"].append(copy.deepcopy(r["contacts"][0])),
                         lambda r: r["mesh"]["vertices"][8].__setitem__(0, 1.1),
                         lambda r: r["boundaries"].extend(boundary([r["contacts"][0]["left_vertices"]], "adiabatic"))):
            raw = contact_request()
            mutation(raw)
            with self.assertRaises(AssemblyTetraThermalError):
                run_assembly_tetra_thermal(raw)

    def test_overlapping_body_interiors_and_same_body_duplicate_nodes(self):
        raw = contact_request()
        raw["contacts"] = []
        raw["boundaries"] = []
        for point in raw["mesh"]["vertices"][8:]:
            point[0] -= .1
        with self.assertRaisesRegex(AssemblyTetraThermalError, "Overlapping"):
            run_assembly_tetra_thermal(raw)
        raw = contact_request()
        raw["mesh"]["object_map"]["right"]["body_id"] = "left"
        with self.assertRaisesRegex(AssemblyTetraThermalError, "Duplicate-coordinate"):
            run_assembly_tetra_thermal(raw)

    def test_same_body_hanging_vertex_rejected(self):
        mesh = cube()
        mesh["vertices"] = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
                            [.5, 0, 0], [0, -1, 0], [0, 0, -1]]
        mesh["cells"] = [{"id": "a", "kind": "tetrahedron", "vertices": [0, 1, 2, 3],
                          "material_id": "k", "source_object_ids": ["solid"]},
                         {"id": "b", "kind": "tetrahedron", "vertices": [0, 4, 5, 6],
                          "material_id": "k", "source_object_ids": ["solid"]}]
        mesh["counts"] = {"vertices": 7, "cells": 2}
        raw = request(mesh)
        raw["boundaries"] = []
        with self.assertRaisesRegex(AssemblyTetraThermalError, "hanging"):
            run_assembly_tetra_thermal(raw)


if __name__ == "__main__":
    unittest.main()
