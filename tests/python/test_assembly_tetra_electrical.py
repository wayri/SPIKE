# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 SigHarmonic
"""Original analytical resistance, conservation and manufactured DC fixtures."""
import copy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core.solvers.power_integrity.dc.assembly_tetra_electrical import AssemblyTetraElectricalError, solve_assembly_tetra_electrical
from tests.python.test_assembly_tetra_thermal import contact_request, cube, faces_at


def request(mesh=None):
    mesh = mesh or cube()
    return {"contract": "spike/assembly-tetra-electrical-request/v1", "mesh": mesh,
            "conductivity_s_m": {c["id"]: 2. for c in mesh["cells"]},
            "terminals": [{"id": f"terminal-{side}-{j}", "vertices": face, "voltage_v": voltage}
                          for side, voltage in ((0, 0.), (1, 1.))
                          for j, face in enumerate(faces_at(mesh, side))]}


def contact_case():
    thermal = contact_request()
    raw = request(thermal["mesh"])
    raw["terminals"] = [{"id": f"terminal-{side}-{j}", "vertices": face, "voltage_v": voltage}
                        for side, voltage in ((0, 0.), (2, 1.))
                        for j, face in enumerate(faces_at(raw["mesh"], side))]
    raw["contacts"] = [{"id": item["id"], "left_vertices": item["left_vertices"],
                        "right_vertices": item["right_vertices"], "electrical_contact_conductance_s_m2": 4.}
                       for item in thermal["contacts"]]
    return raw


class AssemblyTetraElectricalTests(unittest.TestCase):
    def test_analytical_slab_current_heat_units_and_no_mutation(self):
        raw = request(cube(2))
        before = copy.deepcopy(raw)
        result = solve_assembly_tetra_electrical(raw)
        self.assertEqual(raw, before)
        np.testing.assert_allclose(result["node_potential_v"], [p[0] for p in raw["mesh"]["vertices"]], atol=1e-11)
        np.testing.assert_allclose(list(result["cell_joule_heat_w_m3"].values()), 2., atol=1e-10)
        self.assertAlmostEqual(result["joule_power_w"], 2., places=10)
        self.assertAlmostEqual(result["source_power_w"], 2., places=10)
        self.assertAlmostEqual(sum(v for k, v in result["terminal_currents_a"].items() if k.startswith("terminal-1")), 2., places=10)
        self.assertAlmostEqual(sum(result["terminal_currents_a"].values()), 0., places=10)
        self.assertEqual(result["model_status"], "experimental")
        self.assertFalse(result["production_qualified"])
        self.assertLess(abs(result["conservation_residual_w"]), 1e-10)
        raw["mesh"]["units"] = "mm"
        raw["mesh"]["vertices"] = [[1000 * x for x in p] for p in raw["mesh"]["vertices"]]
        converted = solve_assembly_tetra_electrical(raw)
        self.assertAlmostEqual(converted["source_power_w"], 2., places=10)
        np.testing.assert_allclose(converted["node_potential_v"], result["node_potential_v"], atol=1e-11)

    def test_absolute_gauge_and_no_excitation(self):
        raw = request(cube(2))
        for terminal in raw["terminals"]:
            terminal["voltage_v"] += 1e12
        out = solve_assembly_tetra_electrical(raw)
        self.assertAlmostEqual(out["source_power_w"], 2., places=10)
        np.testing.assert_allclose(list(out["cell_joule_heat_w_m3"].values()), 2., atol=1e-10)
        for terminal in raw["terminals"]:
            terminal["voltage_v"] = -3.
        out = solve_assembly_tetra_electrical(raw)
        self.assertEqual(out["source_power_w"], 0.)
        self.assertEqual(out["joule_power_w"], 0.)
        self.assertEqual(out["node_potential_v"], [-3.] * 27)

    def test_matched_contact_current_drop_exact_power_and_allocation(self):
        raw = contact_case()
        out = solve_assembly_tetra_electrical(raw)
        # Two length-1 sigma-2 solids and area-1 g-4 interface: R=1.25 ohm.
        self.assertAlmostEqual(out["source_power_w"], .8, places=10)
        self.assertAlmostEqual(out["joule_power_w"], .64, places=10)
        self.assertAlmostEqual(out["contact_power_w"], .16, places=10)
        self.assertAlmostEqual(sum(c["current_a"] for c in out["contacts"]), -.8, places=10)
        for contact in out["contacts"]:
            self.assertAlmostEqual(contact["mean_voltage_jump_v"], -.2, places=10)
            self.assertAlmostEqual(contact["left_mean_voltage_v"], .4, places=10)
            self.assertAlmostEqual(contact["right_mean_voltage_v"], .6, places=10)
            self.assertEqual(list(contact["loss_allocations_w"].values()), [contact["power_w"] / 2] * 2)
        self.assertAlmostEqual(sum(out["contact_loss_allocations_w"].values()), .16, places=10)
        self.assertAlmostEqual(sum(out["cell_power_w"].values()) + sum(out["contact_loss_allocations_w"].values()), .8, places=10)

    def test_nonuniform_contact_jump_uses_exact_triangle_mass(self):
        raw = contact_case()
        raw["contacts"][0]["electrical_contact_conductance_s_m2"] = 1.
        out = solve_assembly_tetra_electrical(raw)
        potentials = np.array(out["node_potential_v"])
        total_mean_approximation = 0.
        for item, result in zip(raw["contacts"], out["contacts"]):
            left = item["left_vertices"]
            right = [next(i for i in item["right_vertices"] if raw["mesh"]["vertices"][i] == raw["mesh"]["vertices"][j]) for j in left]
            jump = potentials[left] - potentials[right]
            g = item["electrical_contact_conductance_s_m2"]
            exact = .5 * g * (np.dot(jump, jump) + np.sum(jump)**2) / 12
            self.assertAlmostEqual(result["power_w"], exact, places=12)
            total_mean_approximation += .5 * g * np.mean(jump)**2
        self.assertGreater(out["contact_power_w"], total_mean_approximation + 1e-6)

    def test_zero_conductivity_cells_and_inactive_nodes(self):
        raw = contact_case()
        raw.pop("contacts")
        raw["terminals"] = [t for t in raw["terminals"] if t["id"].startswith("terminal-0")]
        for cid in raw["conductivity_s_m"]:
            if cid.startswith("right"):
                raw["conductivity_s_m"][cid] = 0.
        out = solve_assembly_tetra_electrical(raw)
        self.assertEqual(out["node_potential_v"][8:], [None] * 8)
        self.assertEqual(out["node_potential_v"][:8], [0.] * 8)
        self.assertEqual(sum(out["cell_power_w"].values()), 0.)
        raw["conductivity_s_m"] = dict.fromkeys(raw["conductivity_s_m"], 0.)
        raw["terminals"] = []
        out = solve_assembly_tetra_electrical(raw)
        self.assertEqual(out["node_potential_v"], [None] * 16)
        self.assertEqual(out["resources"]["conductive_components"], 0)

    def test_shared_occurrence_distinct_bodies_do_not_weld(self):
        raw = contact_case()
        for source, record in raw["mesh"]["object_map"].items():
            record.update(occurrence_id="assembly", body_id=source)
        self.assertAlmostEqual(solve_assembly_tetra_electrical(raw)["source_power_w"], .8, places=10)
        raw["mesh"]["cells"][6]["vertices"][0] = 0
        with self.assertRaisesRegex(AssemblyTetraElectricalError, "share electrical node"):
            solve_assembly_tetra_electrical(raw)

    def test_manufactured_variable_conductivity_four_grids(self):
        # sigma(x)=1+x, phi=ln(1+x)/ln(2), I=1/ln(2) for unit area.
        # Cell-centroid sampling converges with the independently generated grid.
        errors, powers = [], []
        for refinement in (1, 2, 3, 4):
            raw = request(cube(refinement))
            xyz = np.array(raw["mesh"]["vertices"])
            raw["conductivity_s_m"] = {c["id"]: float(1 + xyz[c["vertices"], 0].mean()) for c in raw["mesh"]["cells"]}
            out = solve_assembly_tetra_electrical(raw)
            potential = np.array(out["node_potential_v"])
            error = 0.
            for cell in raw["mesh"]["cells"]:
                x = xyz[cell["vertices"], 0].mean()
                error += (potential[cell["vertices"]].mean() - math.log1p(x) / math.log(2))**2 / len(raw["mesh"]["cells"])
            errors.append(math.sqrt(error))
            powers.append(abs(out["source_power_w"] - 1 / math.log(2)))
        self.assertTrue(all(b < a for a, b in zip(errors, errors[1:])), errors)
        self.assertTrue(all(b < a for a, b in zip(powers, powers[1:])), powers)
        self.assertLess(errors[-1], errors[0] / 8)
        self.assertLess(powers[-1], .006)

    def test_invalid_contracts_materials_faces_and_nonfinite(self):
        edits = [lambda r: r.update(contract="bad"), lambda r: r.update(transient=True),
                 lambda r: r["conductivity_s_m"].pop("solid-0"),
                 lambda r: r["conductivity_s_m"].update(unknown=1),
                 lambda r: r["conductivity_s_m"].update({"solid-0": -1}),
                 lambda r: r["conductivity_s_m"].update({"solid-0": [[1, 0, 0]] * 3}),
                 lambda r: r["conductivity_s_m"].update({"solid-0": True}),
                 lambda r: r["conductivity_s_m"].update({"solid-0": float("inf")}),
                 lambda r: r["terminals"][0].update(voltage_v=float("nan")),
                 lambda r: r["terminals"][1].update(voltage_v=1),
                 lambda r: r["terminals"].append(copy.deepcopy(r["terminals"][0])),
                 lambda r: r["mesh"]["cells"][0].update(vertices=[0, 0, 1, 2]),
                 lambda r: r["mesh"]["vertices"][0].__setitem__(0, 1e301)]
        for edit in edits:
            raw = request()
            edit(raw)
            with self.subTest(edit=edit), self.assertRaises(AssemblyTetraElectricalError):
                solve_assembly_tetra_electrical(raw)

    def test_floating_contacts_insulators_and_bad_geometry_rejected(self):
        raw = request()
        raw["terminals"] = []
        with self.assertRaisesRegex(AssemblyTetraElectricalError, "Unanchored"):
            solve_assembly_tetra_electrical(raw)
        for edit in (lambda r: r["conductivity_s_m"].update({"right-0": 0.}),
                     lambda r: r["contacts"][0].update(electrical_contact_conductance_s_m2=0),
                     lambda r: r["mesh"]["object_map"]["right"].update(body_id="same"),
                     lambda r: r["mesh"]["vertices"][8].__setitem__(0, 1.1)):
            raw = contact_case()
            # For the owner test both sources must declare the same body.
            raw["mesh"]["object_map"]["left"]["body_id"] = "same"
            edit(raw)
            with self.subTest(edit=edit), self.assertRaises(AssemblyTetraElectricalError):
                solve_assembly_tetra_electrical(raw)

    def test_nonconforming_duplicate_coordinate_nodes_rejected(self):
        raw = request()
        mesh = raw["mesh"]
        mesh["vertices"].append(list(mesh["vertices"][0]))
        mesh["cells"][0]["vertices"][0] = 8
        mesh["counts"]["vertices"] = 9
        with self.assertRaisesRegex(AssemblyTetraElectricalError, "Duplicate-coordinate"):
            solve_assembly_tetra_electrical(raw)

    def test_hanging_vertex_and_overlapping_bodies_rejected(self):
        mesh = cube()
        mesh["vertices"] = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1],
                            [.5, 0, 0], [0, -1, 0], [0, 0, -1]]
        mesh["cells"] = [{"id": "a", "kind": "tetrahedron", "vertices": [0, 1, 2, 3],
                          "material_id": "k", "source_object_ids": ["solid"]},
                         {"id": "b", "kind": "tetrahedron", "vertices": [0, 4, 5, 6],
                          "material_id": "k", "source_object_ids": ["solid"]}]
        mesh["counts"] = {"vertices": 7, "cells": 2}
        raw = request(mesh)
        raw["terminals"] = []
        with self.assertRaisesRegex(AssemblyTetraElectricalError, "hanging"):
            solve_assembly_tetra_electrical(raw)
        raw = contact_case()
        raw["contacts"] = []
        for point in raw["mesh"]["vertices"][8:]:
            point[0] -= .1
        with self.assertRaisesRegex(AssemblyTetraElectricalError, "Overlapping"):
            solve_assembly_tetra_electrical(raw)

    def test_weak_contact_ill_conditioning_and_sparse_eigen_path(self):
        raw = contact_case()
        raw["terminals"] = [t for t in raw["terminals"] if t["id"].startswith("terminal-0")]
        for contact in raw["contacts"]:
            contact["electrical_contact_conductance_s_m2"] = 1e-15
        with self.assertRaisesRegex(AssemblyTetraElectricalError, "conditioning budget"):
            solve_assembly_tetra_electrical(raw)
        out = solve_assembly_tetra_electrical(request(cube(6)))
        self.assertAlmostEqual(out["source_power_w"], 2., places=9)
        self.assertLess(out["diagnostics"]["scaled_condition_estimate"], 1e4)

    def test_bounded_iteration_failure_and_condition_screen(self):
        raw = request(cube(2))
        with patch("python.spike_core.solvers.power_integrity.dc.assembly_tetra_electrical.cg", return_value=(np.zeros(9), 1)):
            with self.assertRaisesRegex(AssemblyTetraElectricalError, "CG"):
                solve_assembly_tetra_electrical(raw)
        with patch("python.spike_core.solvers.power_integrity.dc.assembly_tetra_electrical.np.linalg.eigvalsh", return_value=np.array([1e-20, 1.])):
            with self.assertRaises(AssemblyTetraElectricalError):
                solve_assembly_tetra_electrical(raw)


if __name__ == "__main__":
    unittest.main()
