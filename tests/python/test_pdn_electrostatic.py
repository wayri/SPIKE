# SPDX-License-Identifier: Apache-2.0
"""Original finite-plate and layered-dielectric electrostatic witnesses.

The retained cube generator is reused, not an external mesh. Expected C is
independently derived from epsilon*A/d and series dielectric voltage division.
These fixtures qualify those supplied finite insulating-boundary geometries,
not arbitrary PCB geometry or infinite-domain fringing.
"""
from copy import deepcopy
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import pdn_electrostatic as electrostatic
from tests.python.test_assembly_tetra_thermal import cube

EPSILON_0 = 8.8541878128e-12


def plate(n=1, epsilon=4 * EPSILON_0):
    mesh = cube(n)
    return {"contract": electrostatic.REQUEST_CONTRACT, "mesh": mesh,
            "materials": [{"id": "k", "permittivity_f_m": epsilon}],
            "electrodes": [{"id": "ground-plate", "node": "return-terminal",
                            "vertices": [i for i, p in enumerate(mesh["vertices"]) if p[0] == 0]},
                           {"id": "signal-plate", "node": "load-terminal",
                            "vertices": [i for i, p in enumerate(mesh["vertices"]) if p[0] == 1]}],
            "reference_electrode": "ground-plate", "outer_boundary": "insulating",
            "context_digest": "a" * 64}


class PdnElectrostaticTests(unittest.TestCase):
    def test_actual_plate_refinements_scalar_and_anisotropic(self):
        for epsilon in (4 * EPSILON_0, (EPSILON_0 * np.diag([3., 5., 7.])).tolist()):
            expected = epsilon if isinstance(epsilon, float) else 3 * EPSILON_0
            for refinement in (1, 2, 3):
                request = plate(refinement, epsilon)
                original = deepcopy(request)
                result = electrostatic.extract_pdn_electrostatic(request)
                with self.subTest(epsilon=epsilon, refinement=refinement):
                    self.assertEqual(request, original)
                    self.assertAlmostEqual(result["matrix_f"][0][0] / expected, 1., places=11)
                    self.assertLess(result["diagnostics"]["relative_charge_energy_error"], 1e-11)
                    np.testing.assert_allclose(np.array(result["basis_node_potential_v"])[:, 0],
                                               [p[0] for p in request["mesh"]["vertices"]], atol=1e-11)
                    self.assertEqual(result["model_status"], "experimental")
                    self.assertFalse(result["production_qualified"])

    def test_si_mm_conversion_and_input_mesh_binding(self):
        request = plate(2)
        base = electrostatic.extract_pdn_electrostatic(request)
        request["mesh"]["units"] = "mm"
        request["mesh"]["vertices"] = [[1000 * v for v in p] for p in request["mesh"]["vertices"]]
        converted = electrostatic.extract_pdn_electrostatic(request)
        np.testing.assert_allclose(converted["matrix_f"], base["matrix_f"], rtol=1e-12, atol=0)
        self.assertNotEqual(converted["mesh_digest"], base["mesh_digest"])
        self.assertNotEqual(converted["input_digest"], base["input_digest"])
        self.assertEqual(converted["context_digest"], "a" * 64)

    def test_anisotropic_directional_permittivity(self):
        for axis, multiplier in enumerate([3., 5., 7.]):
            request = plate(2, (EPSILON_0 * np.diag([3., 5., 7.])).tolist())
            for side, electrode in enumerate(request["electrodes"]):
                electrode["vertices"] = [i for i, p in enumerate(request["mesh"]["vertices"]) if p[axis] == side]
            result = electrostatic.extract_pdn_electrostatic(request)
            with self.subTest(axis=axis):
                self.assertAlmostEqual(result["matrix_f"][0][0] / (EPSILON_0 * multiplier), 1., places=11)
                self.assertEqual(result["electrode_lineage"][0]["dielectric_source_object_ids"], ["solid"])

    def test_series_dielectric_independent_charge_oracle(self):
        request = plate(2, 2 * EPSILON_0)
        request["materials"].append({"id": "second", "permittivity_f_m": 8 * EPSILON_0})
        for cell in request["mesh"]["cells"]:
            x = np.mean([request["mesh"]["vertices"][i][0] for i in cell["vertices"]])
            if x > .5:
                cell["material_id"] = "second"
        result = electrostatic.extract_pdn_electrostatic(request)
        expected = 1 / (.5 / (2 * EPSILON_0) + .5 / (8 * EPSILON_0))
        self.assertAlmostEqual(result["matrix_f"][0][0] / expected, 1., places=11)
        self.assertAlmostEqual(result["electrode_basis_charge_c"]["ground-plate"][0] / expected, -1., places=11)

    def test_multiconductor_energy_preserves_coupling(self):
        request = plate(2, EPSILON_0)
        request["electrodes"].insert(1, {"id": "middle", "node": "intermediate-terminal",
            "vertices": [i for i, p in enumerate(request["mesh"]["vertices"]) if p[0] == .5]})
        result = electrostatic.extract_pdn_electrostatic(request)
        matrix = np.array(result["matrix_f"])
        np.testing.assert_allclose(matrix / EPSILON_0, [[4., -2.], [-2., 2.]], rtol=1e-12, atol=1e-12)
        voltage = np.array([2., -3.])
        # Two half-metre gaps: E = eps * ((2-0)^2 + (-3-2)^2).
        expected_energy = 29 * EPSILON_0
        self.assertAlmostEqual(.5 * voltage @ matrix @ voltage / expected_energy, 1., places=11)
        self.assertAlmostEqual(.5 * voltage @ np.array(result["field_energy_matrix_f"]) @ voltage /
                               expected_energy, 1., places=11)
        self.assertEqual(result["nodes"], ["intermediate-terminal", "load-terminal"])

    def test_mesh_terminal_and_material_rejections(self):
        def invert(r):
            nodes = r["mesh"]["cells"][0]["vertices"]
            nodes[0], nodes[1] = nodes[1], nodes[0]
        mutations = [invert,
            lambda r: r.update(reference_electrode="GND"),
            lambda r: r.update(outer_boundary="infinite"),
            lambda r: r.update(ignored=True),
            lambda r: r["electrodes"][0].update(vertices=[0]),
            lambda r: r["electrodes"][0].update(vertices=r["electrodes"][1]["vertices"]),
            lambda r: r["materials"][0].update(permittivity_f_m=-EPSILON_0),
            lambda r: r["materials"][0].update(permittivity_f_m=True),
            lambda r: r["materials"][0].update(permittivity_f_m=[[1, 1, 0], [0, 1, 0], [0, 0, 1]]),
            lambda r: r["materials"][0].update(permittivity_f_m=[[1, 0, 0], [0, -1, 0], [0, 0, 1]]),
            lambda r: r["mesh"]["vertices"][0].__setitem__(0, float("nan")),
            lambda r: r["mesh"]["cells"][0].update(material_id="missing")]
        for mutate in mutations:
            request = plate(2)
            mutate(request)
            with self.subTest(mutation=mutate), self.assertRaises(electrostatic.PdnElectrostaticError):
                electrostatic.extract_pdn_electrostatic(request)

    def test_corrupt_reactions_and_failed_free_solve_are_not_results(self):
        reactions = electrostatic._electrode_reactions
        def wrong_charge(*args):
            charge, nodal = reactions(*args)
            return 1.1 * charge, nodal
        with patch.object(electrostatic, "_electrode_reactions", wrong_charge):
            with self.assertRaisesRegex(electrostatic.PdnElectrostaticError, "energy"):
                electrostatic.extract_pdn_electrostatic(plate(2))
        def wrong_solve(operator, rhs, **kwargs):
            return np.zeros_like(rhs), 0
        with patch.object(electrostatic, "cg", wrong_solve):
            with self.assertRaisesRegex(electrostatic.PdnElectrostaticError, "residual"):
                electrostatic.extract_pdn_electrostatic(plate(2))


if __name__ == "__main__":
    unittest.main()
