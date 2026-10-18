# SPDX-License-Identifier: Apache-2.0
"""Original finite-plate and layered complex-admittance analytical witnesses."""
from copy import deepcopy
import math
import unittest
from unittest.mock import patch

import numpy as np

from python.spike_core import pdn_dielectric_ac as dielectric
from tests.python.test_pdn_electrostatic import plate as electrostatic_plate


def plate(n=2, epsilon=4e-8, sigma=1e-6, tangent=.2, frequencies=None):
    request = electrostatic_plate(n, epsilon)
    request["contract"] = dielectric.REQUEST_CONTRACT
    request["frequencies_hz"] = frequencies or [1000., 100000.]
    request["materials"][0].update(conductivity_s_m=sigma, loss_tangent=tangent)
    return request


def complex_values(values):
    if isinstance(values, dict):
        return complex(values["real"], values["imag"])
    return np.array([complex_values(item) for item in values])


def layered(n=2):
    request = plate(n, 2e-6, 4e-5, .03, [1., 10., 100.])
    request["materials"].append({"id": "second", "permittivity_f_m": 8e-6,
                                 "conductivity_s_m": 2e-6, "loss_tangent": .5})
    for cell in request["mesh"]["cells"]:
        if np.mean([request["mesh"]["vertices"][index][0] for index in cell["vertices"]]) > .5:
            cell["material_id"] = "second"
    return request


def gamma(material, frequency):
    omega = 2 * math.pi * frequency
    return material["conductivity_s_m"] + omega * material["permittivity_f_m"] * (material["loss_tangent"] + 1j)


class PdnDielectricAcTests(unittest.TestCase):
    def test_homogeneous_plate_refinements_and_full_fields(self):
        for epsilon in (4e-8, np.diag([3e-8, 5e-8, 7e-8]).tolist()):
            directional = epsilon if isinstance(epsilon, float) else epsilon[0][0]
            for refinement in (1, 2, 3):
                with self.subTest(epsilon=epsilon, refinement=refinement):
                    req = plate(refinement, epsilon)
                    before = deepcopy(req)
                    result = dielectric.extract_pdn_dielectric_ac(req)
                    self.assertEqual(req, before)
                    self.assertEqual(result["model_status"], "experimental")
                    self.assertFalse(result["production_qualified"])
                    self.assertEqual(result["nodes"], ["load-terminal"])
                    self.assertEqual(result["electrode_lineage"][0]["dielectric_source_object_ids"], ["solid"])
                    for response in result["ac"]:
                        omega = 2 * math.pi * response["frequency_hz"]
                        expected = 1e-6 + omega * directional * (.2 + 1j)
                        actual = complex_values(response["admittance_s"])[0, 0]
                        self.assertLess(abs(actual / expected - 1), 2e-12)
                        np.testing.assert_allclose(complex_values(response["basis_node_potential_v"])[:, 0],
                                                   [p[0] for p in req["mesh"]["vertices"]], atol=2e-12, rtol=0)
                        fields = complex_values(response["basis_cell_electric_field_v_m"])[:, :, 0]
                        np.testing.assert_allclose(fields, np.tile([-1., 0., 0.], (len(fields), 1)), atol=2e-11, rtol=0)
                        self.assertLess(response["diagnostics"]["relative_power_identity_error"], 2e-12)

    def test_differing_loss_layers_actual_complex_fields_at_refinements(self):
        for refinement in (2, 4):
            req = layered(refinement)
            result = dielectric.extract_pdn_dielectric_ac(req)
            for response in result["ac"]:
                g1, g2 = [gamma(m, response["frequency_hz"]) for m in req["materials"]]
                expected = 1 / (.5 / g1 + .5 / g2)
                interface = .5 * expected / g1
                actual = complex_values(response["admittance_s"])[0, 0]
                self.assertLess(abs(actual / expected - 1), 3e-12)
                self.assertGreater(abs(interface.imag), .01)
                # A lossless reuse would give a real interface potential .8,
                # whereas unequal loss ratios require a complex field solve.
                expected_potential = [expected * x / g1 if x <= .5 else interface + expected * (x - .5) / g2
                                      for x, _, _ in req["mesh"]["vertices"]]
                np.testing.assert_allclose(complex_values(response["basis_node_potential_v"])[:, 0],
                                           expected_potential, rtol=2e-12, atol=2e-12)
                fields = complex_values(response["basis_cell_electric_field_v_m"])[:, :, 0]
                expected_fields = [[-expected / (g1 if c["material_id"] == "k" else g2), 0., 0.]
                                   for c in req["mesh"]["cells"]]
                np.testing.assert_allclose(fields, expected_fields, rtol=2e-12, atol=2e-11)

    def test_multielectrode_coupling_conjugate_power_and_reference_order(self):
        req = layered(2)
        req["electrodes"].insert(1, {"id": "middle", "node": "middle-node",
            "vertices": [i for i, p in enumerate(req["mesh"]["vertices"]) if p[0] == .5]})
        # Reference is deliberately not the first electrode.
        req["electrodes"] = [req["electrodes"][1], req["electrodes"][0], req["electrodes"][2]]
        result = dielectric.extract_pdn_dielectric_ac(req)
        self.assertEqual(result["nodes"], ["middle-node", "load-terminal"])
        voltage = np.array([2. + 1j, -3. + .5j])
        for response in result["ac"]:
            y1, y2 = [2 * gamma(material, response["frequency_hz"]) for material in req["materials"]]
            expected = np.array([[y1 + y2, -y2], [-y2, y2]])
            actual = complex_values(response["admittance_s"])
            np.testing.assert_allclose(actual, expected, rtol=2e-12, atol=1e-15)
            power = voltage.conj() @ actual @ voltage
            exact_power = abs(voltage[0])**2 * y1 + abs(voltage[1] - voltage[0])**2 * y2
            self.assertLess(abs(power / exact_power - 1), 2e-12)
            self.assertGreater(power.real, 0.)
            # Returned field form is V^H I; conventional RMS complex power
            # V^T I* is its conjugate, with the same average dissipation.
            conventional = voltage @ (actual @ voltage).conj()
            self.assertAlmostEqual(conventional.real, power.real, delta=1e-12)
            self.assertAlmostEqual(conventional.imag, -power.imag, delta=1e-12)
            field_form = complex_values(response["field_power_matrix_s"])
            np.testing.assert_allclose(field_form, expected, rtol=2e-12, atol=1e-15)
            current = sum(complex_values(row) for row in response["electrode_basis_current_a"].values())
            np.testing.assert_allclose(current, 0., atol=1e-15)
            self.assertGreaterEqual(np.linalg.eigvalsh((actual + actual.conj().T) / 2)[0], 0.)

    def test_lossless_limit_and_si_mesh_digest_binding(self):
        req = plate(2, 4e-8, 0., 0.)
        base = dielectric.extract_pdn_dielectric_ac(req)
        for response in base["ac"]:
            actual = complex_values(response["admittance_s"])[0, 0]
            self.assertAlmostEqual(actual.real, 0., delta=1e-15)
            self.assertLess(abs(actual / (2j * math.pi * response["frequency_hz"] * 4e-8) - 1), 2e-12)
        req["mesh"]["units"] = "mm"
        small = dielectric.extract_pdn_dielectric_ac(req)
        for left, right in zip(base["ac"], small["ac"]):
            np.testing.assert_allclose(complex_values(right["admittance_s"]),
                                       1e-3 * complex_values(left["admittance_s"]), rtol=2e-12)
            np.testing.assert_allclose(complex_values(right["basis_cell_electric_field_v_m"]),
                                       1e3 * complex_values(left["basis_cell_electric_field_v_m"]), rtol=2e-12, atol=2e-9)
        req["mesh"]["vertices"] = [[1000 * value for value in p] for p in req["mesh"]["vertices"]]
        converted = dielectric.extract_pdn_dielectric_ac(req)
        for left, right in zip(base["ac"], converted["ac"]):
            np.testing.assert_allclose(complex_values(left["admittance_s"]), complex_values(right["admittance_s"]), rtol=2e-12)
        self.assertNotEqual(base["mesh_digest"], converted["mesh_digest"])
        self.assertNotEqual(base["input_digest"], converted["input_digest"])
        self.assertEqual(base["context_digest"], converted["context_digest"])

    def test_anisotropic_directional_admittance(self):
        for axis, epsilon in enumerate((3e-8, 5e-8, 7e-8)):
            req = plate(2, np.diag([3e-8, 5e-8, 7e-8]).tolist())
            for side, electrode in enumerate(req["electrodes"]):
                electrode["vertices"] = [i for i, p in enumerate(req["mesh"]["vertices"]) if p[axis] == side]
            for response in dielectric.extract_pdn_dielectric_ac(req)["ac"]:
                expected = 1e-6 + 2 * math.pi * response["frequency_hz"] * epsilon * (.2 + 1j)
                self.assertLess(abs(complex_values(response["admittance_s"])[0, 0] / expected - 1), 2e-12)

    def test_extreme_finite_operator_norm_is_rejected(self):
        # Finite entries can still overflow squared Frobenius norms. They
        # must not turn passivity tolerances into infinity or reach JSON NaN.
        with self.assertRaises(dielectric.PdnDielectricAcError) as caught:
            dielectric.extract_pdn_dielectric_ac(plate(1, sigma=1e200))
        self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_AC_NUMERICAL_FAILURE")

    def test_strict_material_frequency_and_geometry_admission(self):
        mutations = [lambda r: r.update(frequencies_hz=[0.]), lambda r: r.update(frequencies_hz=[2., 1.]),
            lambda r: r.update(frequencies_hz=[1., 1.]), lambda r: r.update(frequencies_hz=[True]),
            lambda r: r.update(frequencies_hz=[1e308]), lambda r: r.update(outer_boundary="infinite"),
            lambda r: r["materials"][0].update(conductivity_s_m=-1.),
            lambda r: r["materials"][0].update(conductivity_s_m=[[1., 0., 0.]]),
            lambda r: r["materials"][0].update(loss_tangent=True),
            lambda r: r["materials"][0].update(loss_tangent=-.1),
            lambda r: r["materials"][0].update(permittivity_f_m=[[1., 0., 0.], [0., -1., 0.], [0., 0., 1.]]),
            lambda r: r["electrodes"][0].update(vertices=r["electrodes"][1]["vertices"]),
            lambda r: r.update(extra=True)]
        for index, mutate in enumerate(mutations):
            req = plate()
            mutate(req)
            with self.subTest(case=index), self.assertRaises(dielectric.PdnDielectricAcError) as caught:
                dielectric.extract_pdn_dielectric_ac(req)
            self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_AC_INVALID_REQUEST")

    def test_bounded_work_fields_mesh_and_frequency_before_linear_solve(self):
        for attribute, limit in (("_MAX_FREE", 8), ("_MAX_DENSE_WORK", 1), ("_MAX_RESULT_BYTES", 1),
                                 ("_MAX_NODES", 8), ("_MAX_CELLS", 6), ("_MAX_FREQUENCIES", 1)):
            with self.subTest(bound=attribute), patch.object(dielectric, attribute, limit), \
                    patch.object(dielectric, "_solve_linear") as solve:
                with self.assertRaises(dielectric.PdnDielectricAcError) as caught:
                    dielectric.extract_pdn_dielectric_ac(plate())
                self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_AC_RESOURCE_LIMIT")
                solve.assert_not_called()

    def test_corrupt_free_solution_and_electrode_currents_are_rejected(self):
        with patch.object(dielectric, "_solve_linear", side_effect=lambda matrix, rhs, where: (np.zeros_like(rhs), 0., 1.)):
            with self.assertRaisesRegex(dielectric.PdnDielectricAcError, "residual"):
                dielectric.extract_pdn_dielectric_ac(plate())
        reaction = dielectric._electrode_reactions

        def wrong_current(*args):
            currents, nodal = reaction(*args)
            return 1.1 * currents, nodal

        with patch.object(dielectric, "_electrode_reactions", side_effect=wrong_current):
            with self.assertRaisesRegex(dielectric.PdnDielectricAcError, "power"):
                dielectric.extract_pdn_dielectric_ac(plate())

    def test_conditioning_rejection_and_frequency_loop_cancellation(self):
        # Tensor eigenvalue ratio is admitted at 1e12, while the free-node
        # PDE has an equilibrated condition beyond the stricter solve gate.
        req = plate(3, np.diag([1e-12, 1., 1.]).tolist(), 0., 0., [1.])
        with self.assertRaises(dielectric.PdnDielectricAcError) as caught:
            dielectric.extract_pdn_dielectric_ac(req)
        self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_AC_CONDITIONING_FAILURE")
        calls = 0

        def cancel():
            nonlocal calls
            calls += 1
            return calls == 8

        with self.assertRaises(dielectric.PdnDielectricAcError) as caught:
            dielectric.extract_pdn_dielectric_ac(plate(), cancel_check=cancel)
        self.assertEqual(caught.exception.code, "PDN_DIELECTRIC_AC_CANCELLED")
        self.assertEqual(calls, 8)


if __name__ == "__main__":
    unittest.main()
